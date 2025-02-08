"""
Refined Flask Authentication Blueprint with improved password reset logic.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

from email_validator import EmailNotValidError, validate_email
from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from database import db_session
from decorators import admin_required
from extensions import limiter
from forms import LoginForm, RegistrationForm, ResetPasswordForm, ForgotPasswordForm
from models import User
from scripts.send_email import send_email

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

logger = logging.getLogger(__name__)


# -----------------------
# Helper Functions
# -----------------------


def is_safe_url(target: str) -> bool:
    """Validate that a redirect URL is safe"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def json_response(
    success: bool,
    message: str = None,
    data: dict = None,
    errors: dict = None,
    status_code: int = 200,
):
    """Helper for consistent JSON responses"""
    response = {
        "success": success,
        "message": message,
        "data": data or {},
        "errors": errors or {},
    }
    return jsonify(response), status_code


def send_reset_email(email: str, reset_url: str) -> None:
    """Send password reset email to user."""
    try:
        send_email(
            to=email,
            subject="Password Reset Request",
            template="emails/reset_password.html",
            reset_url=reset_url,
            expiry_hours=1,
        )
        logger.info(f"Password reset email sent to {email}")
    except Exception as e:
        logger.error(f"Failed to send password reset email: {str(e)}")
        raise


# -----------------------
# Blueprint Setup
# -----------------------

bp = Blueprint("auth", __name__)


# -----------------------
# Routes
# -----------------------


@bp.route("/manage_users", methods=["GET"])
@login_required
@admin_required
def manage_users():
    """Render the manage users page."""
    logger.info(
        "Accessed manage users page",
        extra={
            "ip_address": request.remote_addr,
            "route": request.path,
            "user_id": current_user.id,
        },
    )
    return render_template("manage_users.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    form = LoginForm()

    if form.validate_on_submit():
        try:
            username = form.username.data.strip()
            password = form.password.data

            logger.debug(f"Login attempt for username: {username}")

            user = User.get_by_username(username)
            if not user:
                logger.warning(f"Login failed - user not found: {username}")
                flash("Invalid credentials", "error")
                return render_template("login.html", form=form)

            if not user.check_password(password):
                logger.warning(f"Invalid password for user: {username}")
                flash("Invalid credentials", "error")
                return render_template("login.html", form=form)

            login_user(user, remember=form.remember.data)
            logger.info(f"User logged in: {user.id} ({username})")

            next_page = request.args.get("next")
            if not next_page or not is_safe_url(next_page):
                next_page = url_for("chat.chat_interface")

            return redirect(next_page)

        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            flash("Temporary authentication issue - please try again", "error")
            return render_template("login.html", form=form)

    return render_template("login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    """Handle user registrations with consistent JSON responses"""
    if current_user.is_authenticated:
        return json_response(
            True, "Already logged in", {"redirect": url_for("chat.chat_interface")}
        )

    form = RegistrationForm()

    if request.method == "POST":
        if not form.validate_on_submit():
            return json_response(
                False, "Form validation failed", errors=form.errors, status_code=400
            )

        try:
            user = User.create(
                username=form.username.data.strip(),
                email=form.email.data.lower().strip(),
                password=form.password.data,
            )

            login_user(user, remember=True)
            session.permanent = True
            session["_fresh"] = True
            session["user_id"] = user.id
            session["last_active"] = datetime.now().isoformat()

            session.modified = True

            return json_response(
                True,
                "Registration successful",
                {"redirect": url_for("chat.chat_interface"), "user": user.to_dict()},
            )

        except ValueError as e:
            logger.error(f"Registration error: {str(e)}")
            return json_response(False, str(e), status_code=400)
        except Exception as e:
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            return json_response(
                False, "Registration failed - please try again", status_code=500
            )

    return render_template("register.html", form=form)


@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    """Handle forgot password requests."""
    form = ForgotPasswordForm()

    if request.method == "POST":
        email = request.form.get("email", "").strip()

        try:
            # Validate email format
            validate_email(email, check_deliverability=False)

            with db_session() as db:
                user = (
                    db.execute(
                        text("SELECT id, email FROM users WHERE email = :email"),
                        {"email": email},
                    )
                    .mappings()
                    .first()
                )

                # Always show success response to prevent email enumeration
                success_message = {
                    "success": True,
                    "message": (
                        "If an account exists with this email, "
                        "you will receive password reset instructions."
                    ),
                }

                if not user:
                    logger.info(
                        "Password reset requested for non-existent email",
                        extra={
                            "ip_address": request.remote_addr,
                            "route": request.path,
                            "email": email,
                        },
                    )
                    return jsonify(success_message), 200

                # If user exists, generate the reset token.
                serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
                reset_token = serializer.dumps(email, salt="password-reset")
                hashed_token = generate_password_hash(reset_token)

                # Update DB with hashed token and expiry
                db.execute(
                    text(
                        """
                        UPDATE users
                        SET reset_token_hash = :token_hash,
                            reset_token_expiry = NOW() + INTERVAL '1 hour'
                        WHERE email = :email
                        """
                    ),
                    {"token_hash": hashed_token, "email": email},
                )

                reset_url = url_for(
                    "auth.reset_password", token=reset_token, _external=True
                )
                send_reset_email(email, reset_url)

                logger.info(
                    "Password reset email sent",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "email": email,
                    },
                )
                return jsonify(success_message), 200

        except EmailNotValidError:
            logger.warning(
                "Invalid email address provided for password reset",
                extra={
                    "ip_address": request.remote_addr,
                    "route": request.path,
                    "email": email,
                },
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Please provide a valid email address.",
                    }
                ),
                400,
            )
        except Exception as e:
            logger.error(
                f"Error during password reset: {e}",
                exc_info=True,
                extra={
                    "ip_address": request.remote_addr,
                    "route": request.path,
                    "email": email,
                },
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "An error occurred. Please try again later.",
                    }
                ),
                500,
            )

    return render_template("forgot_password.html", form=form)


@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token: str):
    """Handle password reset requests."""
    form = ResetPasswordForm()
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

    try:
        # Decode the token to get the email, ensuring it's not expired
        email = serializer.loads(token, salt="password-reset", max_age=3600)

        with db_session() as db:
            user = (
                db.execute(
                    text("SELECT * FROM users WHERE email = :email"),
                    {"email": email},
                )
                .mappings()
                .first()
            )

            if not user:
                logger.warning(
                    "User not found for reset token",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "token": token,
                    },
                )
                return (
                    jsonify(
                        {"success": False, "error": "Invalid or expired reset token."}
                    ),
                    400,
                )

            # Check if token is actually stored and not expired
            if not user["reset_token_hash"] or not user["reset_token_expiry"]:
                logger.warning(
                    "Missing reset token data in DB",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "token": token,
                    },
                )
                return (
                    jsonify(
                        {"success": False, "error": "Invalid or expired reset token."}
                    ),
                    400,
                )

            # Ensure the token hasn't expired
            if user["reset_token_expiry"].replace(tzinfo=timezone.utc) < datetime.now(
                timezone.utc
            ):
                logger.warning(
                    "Reset token has expired",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "token": token,
                    },
                )
                return (
                    jsonify(
                        {"success": False, "error": "Invalid or expired reset token."}
                    ),
                    400,
                )

            # Verify the hashed token matches
            if not check_password_hash(user["reset_token_hash"], token):
                logger.warning(
                    "Reset token mismatch",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "token": token,
                    },
                )
                return (
                    jsonify(
                        {"success": False, "error": "Invalid or expired reset token."}
                    ),
                    400,
                )

            if request.method == "POST" and form.validate_on_submit():
                hashed_password = generate_password_hash(form.password.data.strip())

                db.execute(
                    text(
                        """
                        UPDATE users
                        SET password_hash = :password_hash,
                            reset_token_hash = NULL,
                            reset_token_expiry = NULL
                        WHERE id = :user_id
                        """
                    ),
                    {"password_hash": hashed_password, "user_id": user["id"]},
                )

                logger.info(
                    "Password reset successfully",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "user_id": user["id"],
                    },
                )
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": "Your password has been reset successfully.",
                            "redirect": url_for("auth.login"),
                        }
                    ),
                    200,
                )

            elif request.method == "POST":
                # Form not valid
                logger.warning(
                    "Password reset form validation failed",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "errors": form.errors,
                    },
                )
                return jsonify({"success": False, "errors": form.errors}), 400

            return render_template("reset_password.html", form=form)

    except (SignatureExpired, BadSignature):
        logger.warning(
            "Invalid or expired reset token in URL decoding",
            extra={
                "ip_address": request.remote_addr,
                "route": request.path,
                "token": token,
            },
        )
        return (
            jsonify({"success": False, "error": "Invalid or expired reset token."}),
            400,
        )
    except Exception as e:
        logger.error(
            f"Error during password reset: {e}",
            exc_info=True,
            extra={
                "ip_address": request.remote_addr,
                "route": request.path,
                "token": token,
            },
        )
        return jsonify({"success": False, "error": "An unexpected error occurred"}), 500


@bp.route("/auth/check", methods=["GET"])
@login_required
def check_auth():
    """Verify if the user is logged in."""
    return jsonify({"authenticated": True, "user_id": current_user.id}), 200


@bp.after_request
def cleanup_session(response):
    """Cleanup any lingering session data"""
    try:
        db = getattr(g, "_database", None)
        if db is not None:
            db.close()
    except Exception as e:
        logger.error(f"Session cleanup error: {str(e)}")
    return response


@bp.route("/test-create-user")
def test_create_user():
    """Test route for creating a user with hardcoded data."""
    try:
        user = User.create(
            username=os.getenv("TEST_USERNAME"),
            email=os.getenv("TEST_EMAIL"),
            password=os.getenv("TEST_PASSWORD"),
        )
        # import os
        return jsonify({"success": True, "user_id": user.id}), 200
    except Exception as e:
        logger.error(f"Test user creation failed: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/logout")
@login_required
def logout():
    """Handle user logout with consistent response format"""
    logger.info(
        "User logged out",
        extra={
            "user_id": current_user.id,
            "ip_address": request.remote_addr,
            "route": request.path,
            "session_duration": (
                datetime.now()
                - datetime.fromisoformat(
                    session.get("last_active", datetime.now().isoformat())
                )
            ).total_seconds(),
        },
    )
    logout_user()
    session.clear()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return json_response(
            True, "Logged out successfully", {"redirect": url_for("auth.login")}
        )
    return redirect(url_for("auth.login"))
