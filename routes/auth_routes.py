"""
Refined Flask Authentication Blueprint with improved password reset logic.
"""

import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

from typing import Optional
from flask_wtf.csrf import CSRFError, generate_csrf
from email_validator import EmailNotValidError, validate_email
from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    make_response,
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
    message: Optional[str] = None,
    data: Optional[dict] = None,
    errors: Optional[dict] = None,
    status_code: int = 200,
):
    """Helper for consistent JSON responses"""
    response = {
        "success": success,
        "message": message if message is not None else "",
        "data": data if data is not None else {},
        "errors": errors if errors is not None else {},
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
@limiter.limit("10/minute;100/day")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    form = LoginForm()

    if form.validate_on_submit():
        # Account lockout check
        username = form.username.data
        if not username:
            flash("Username is required", "error")
            return render_template("login.html", form=form)
        user = User.get_by_username(username.strip())
        if user and user.account_locked_until and user.account_locked_until > datetime.now(timezone.utc):
            logger.warning(f"Login attempt for locked account: {user.username}")
            flash("Account locked for 15 minutes due to multiple failed attempts", "error")
            return render_template("login.html", form=form)

        # Add CSRF debugging
        logger.debug(f"CSRF data in form object: {form.csrf_token.data}")
        logger.debug(f"Raw form data for csrf_token: {request.form.get('csrf_token')}")
        logger.debug(f"Cookies sent by client: {request.cookies}")
        # Session-based CSRF validation with token rotation
        session_token = session.get('csrf_token')
        form_token = form.csrf_token.data
        cookie_token = request.cookies.get('X-CSRF-TOKEN')
        header_token = request.headers.get('X-CSRFToken')
        
        # Validate all tokens exist
        if not all([session_token, form_token, cookie_token, header_token]):
            raise CSRFError("Missing CSRF tokens")
        
        # Validate all tokens match
        if len({session_token, form_token, cookie_token, header_token}) != 1:
            raise CSRFError("CSRF token mismatch")
        
        # Rotate CSRF token after validation
        new_token = generate_csrf()
        session['csrf_token'] = new_token
        g.csrf_token = new_token
        try:
            username = form.username.data
            if not username or not isinstance(username, str):
                raise ValueError("Invalid username")
            username = username.strip() if username else ""

            password = form.password.data
            if not password or not isinstance(password, str):
                raise ValueError("Invalid password")

            logger.debug(f"Login attempt for username: {username}")

            user = User.get_by_username(username)
            if not user:
                logger.warning(f"Login failed - user not found: {username}")
                flash("Invalid credentials", "error")
                return render_template("login.html", form=form)

            # Track failed attempts
            if not user.check_password(password):
                with db_session() as db:
                    # Update failed attempts atomically
                    result = db.execute(
                        text("""
                            UPDATE users 
                            SET failed_login_attempts = failed_login_attempts + 1,
                                account_locked_until = CASE 
                                    WHEN failed_login_attempts + 1 >= 5 
                                    THEN NOW() + INTERVAL '15 minutes'
                                    ELSE NULL 
                                END
                            WHERE id = :user_id
                            RETURNING failed_login_attempts
                        """),
                        {"user_id": user.id}
                    ).scalar()
                    
                    attempts = result if result is not None else 1
                    logger.warning(f"Invalid password for user: {username} (Attempt {attempts}/5)")
                    flash("Invalid credentials", "error")
                    return render_template("login.html", form=form)

            # Reset failed attempts on successful login
            with db_session() as db:
                db.execute(
                    text("""
                        UPDATE users
                        SET failed_login_attempts = 0,
                            account_locked_until = NULL
                        WHERE id = :user_id
                    """),
                    {"user_id": user.id}
                )

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


@bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF validation failures."""
    # CSRF validation may fail due to:
    # 1. No Matching Session Cookie: Ensure the request includes the session cookie set by Flask.
    # 2. The Hidden Field Isn’t Submitted: Verify that the <input type="hidden" name="csrf_token"> is included in the form.
    # 3. Secret Key or Session Setup: Confirm that a valid SECRET_KEY is set and session cookies are properly configured.
    # 4. Accessing the Route Incorrectly: External requests (e.g. via Postman) may miss necessary cookies.
    logger.warning(
        "CSRF validation failed",
        extra={
            "ip_address": request.remote_addr,
            "route": request.path,
            "error_type": type(e).__name__,
            "user_agent": request.headers.get("User-Agent"),
            "referrer": request.headers.get("Referer"),
            "headers": dict(request.headers),
            "form_data": request.form.to_dict(),
            "cookies": request.cookies
        }
    )
    
    # Generate new CSRF token for the response
    csrf_token = generate_csrf()
    
    response = make_response({
        "success": False,
        "error": "CSRF validation failed. Please refresh the page.",
        "csrf_token": csrf_token
    })
    response.set_cookie(
        "X-CSRF-TOKEN",
        value=csrf_token,
        secure=True,
        httponly=False,
        samesite='Strict'
    )
    return response

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(response_data), 400  # Return JSON for AJAX requests

    flash("Form validation failed. Please try again.", "error")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"]) 
@limiter.limit("5 per minute")
def register():
    """Handle user registration with form submission"""
    logger.info("Register route accessed - Method: %s", request.method)
    if current_user.is_authenticated:
        logger.info("User already authenticated, redirecting to chat interface")
        return redirect(url_for("chat.chat_interface"))

    form = RegistrationForm()
    
    if form.validate_on_submit():
        try:
            username_data = form.username.data
            if not username_data or not isinstance(username_data, str):
                raise ValueError("Invalid username")
            username = username_data.strip()

            email_data = form.email.data
            if not email_data or not isinstance(email_data, str):
                raise ValueError("Invalid email")
            email = email_data.lower().strip()

            password_data = form.password.data
            if not password_data or not isinstance(password_data, str):
                raise ValueError("Invalid password")

            # Create user
            user = User.create(
                username=username,
                email=email,
                password=password_data
            )

            # Log in the user
            login_user(user)
            session.permanent = True
            session["_fresh"] = True
            session["user_id"] = user.id
            session["last_active"] = datetime.now().isoformat()
            session.modified = True

            # Redirect to chat interface
            return redirect(url_for("chat.chat_interface"))
        
        except Exception as e:
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            flash(str(e), "error")

    return render_template("register.html", form=form)


@bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if current_app.config["ENV"] == "development":
        # No rate limit in development
        limiter.exempt(forgot_password)
    else:
        # 5 per minute in production
        limiter.limit("5 per minute")(forgot_password)
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
                password_data = form.password.data
                if not password_data or not isinstance(password_data, str):
                    raise ValueError("Invalid password")
                
                hashed_password = generate_password_hash(password_data.strip())

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
        username_env = os.getenv("TEST_USERNAME")
        email_env = os.getenv("TEST_EMAIL")
        password_env = os.getenv("TEST_PASSWORD")

        # Provide a fallback or raise an error if any of them is None
        if not username_env:
            username_env = "test-user"
        if not email_env:
            email_env = "test@example.com"
        if not password_env:
            password_env = "TestPassword123"

        user = User.create(
            username=username_env,
            email=email_env,
            password=password_env
        )
        return jsonify({"success": True, "user_id": user.id}), 200
    except Exception as e:
        logger.error(
            f"Test user creation failed: {str(e)}",
            exc_info=True,
            extra={
                "ip_address": request.remote_addr,
                "route": request.path,
                "TEST_USERNAME": os.getenv("TEST_USERNAME"),
                "TEST_EMAIL": os.getenv("TEST_EMAIL")
            }
        )
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
