import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from typing import Optional

from flask import (
    Blueprint,
    current_app,
    make_response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFError, generate_csrf
from email_validator import EmailNotValidError, validate_email
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
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
# Blueprint Setup
# -----------------------
bp = Blueprint("auth", __name__)

# -----------------------
# Helper Functions
# -----------------------

def is_safe_url(target: str) -> bool:
    """Validate that a redirect URL is safe."""
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
    """Helper for consistent JSON responses."""
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
@limiter.limit("20/minute;200/day")
def login():
    logger.info("Login route accessed - Method: %s", request.method)
    
    if current_app.config["ENV"] == "development":
        limiter.exempt(login)
        
    if current_user.is_authenticated:
        logger.debug("User already authenticated, redirecting to chat interface")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"redirect": url_for("chat.chat_interface")}), 200
        if request.accept_mimetypes.accept_json:
            return jsonify({"redirect": url_for("chat.chat_interface")}), 302
        return redirect(url_for("chat.chat_interface"))

    form = LoginForm()
    logger.debug("Login form initialized")

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                user = form.get_user()
                if not user:
                    logger.warning("Login attempt failed - invalid credentials")
                    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                        return jsonify({
                            "success": False,
                            "errors": {"username": ["Invalid username or password"]}
                        }), 400
                    flash("Invalid username or password", "error")
                    return render_template("login.html", form=form)

                # Record successful login attempt
                with db_session() as db:
                    db.execute(
                        text("""
                            INSERT INTO login_attempts (username, ip_address, success, attempted_at)
                            VALUES (:username, :ip, true, NOW())
                        """),
                        {
                            "username": user.username,
                            "ip": request.remote_addr
                        }
                    )

                login_user(user, remember=form.remember.data)
                logger.info(f"User logged in: {user.id} ({user.username})")

                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({
                        "success": True,
                        "redirect": url_for('chat.chat_interface', _external=True),
                        "session_token": user.get_auth_token()
                    })
                return redirect(url_for("chat.chat_interface"))

            except Exception as e:
                logger.error(f"Login error: {str(e)}", exc_info=True)
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({
                        "success": False,
                        "errors": {"login": "An unexpected error occurred"}
                    }), 500
                flash("An unexpected error occurred", "error")
                return render_template("login.html", form=form)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": False,
                "errors": form.errors
            }), 400
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "error")
        return render_template("login.html", form=form)

    return render_template("login.html", form=form)

@bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF validation failures."""
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
    
    csrf_token = session.get('csrf_token') or generate_csrf()
    session['csrf_token'] = csrf_token
    g.csrf_token = csrf_token
    
    response = make_response(jsonify({
        "success": False,
        "error": "Security validation failed. Please refresh the page and try again.",
        "csrf_token": csrf_token
    }), 403)

    response.set_cookie(
        'X-CSRF-TOKEN',
        value=csrf_token,
        secure=True,
        httponly=False,
        samesite='Lax',
        max_age=3600,
        path='/'
    )
    return response

@bp.route("/register", methods=["GET", "POST"]) 
@limiter.limit("5 per minute")
def register():
    """Handle user registration with form submission."""
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

            with db_session() as db:
                user = User.create(
                    db,
                    username=username,
                    email=email,
                    password=password_data
                )
                db.refresh(user)
                login_user(user)

            session.permanent = True
            session["_fresh"] = True
            session["user_id"] = user.id
            session["last_active"] = datetime.now().isoformat()
            session.modified = True

            return redirect(url_for("chat.chat_interface"))
        
        except IntegrityError as e:
            logger.error(f"Registration integrity error: {str(e)}")
            flash("Email address already exists", "error")
            return render_template("register.html", form=form)
        except Exception as e:
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            flash(str(e), "error")

    return render_template("register.html", form=form)

@bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if current_app.config["ENV"] == "development":
        limiter.exempt(forgot_password)
    else:
        limiter.limit("5 per minute")(forgot_password)

    form = ForgotPasswordForm()

    if request.method == "POST":
        email = request.form.get("email", "").strip()

        try:
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

                serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
                reset_token = serializer.dumps(email, salt="password-reset")
                reset_token_str = (
                    reset_token.decode("utf-8") if isinstance(reset_token, bytes)
                    else str(reset_token)
                )
                hashed_token = generate_password_hash(reset_token_str)

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
    form = ResetPasswordForm()
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

    try:
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

            if user["reset_token_expiry"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
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
    """Cleanup any lingering session data."""
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
        username_env = os.getenv("TEST_USERNAME") or "test-user"
        email_env = os.getenv("TEST_EMAIL") or "test@example.com"
        password_env = os.getenv("TEST_PASSWORD") or "TestPassword123"

        with db_session() as db:
            user = User.create(
                db,
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
    """Handle user logout with consistent response format."""
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
