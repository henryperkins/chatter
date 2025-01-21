"""
Authentication routes for the application.
"""

import logging
import os
import secrets, hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from email_validator import validate_email
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError, validate_csrf
from wtforms.validators import ValidationError
from sqlalchemy import text

from chat_utils import handle_error, send_reset_email
from config import Config
from database import db_session  # Import db_session from centralized database module
from decorators import admin_required
from extensions import limiter
from forms import LoginForm, RegistrationForm, ResetPasswordForm
from models import Model, User, user
from .auth_utils import (  # Remove db_session from auth_utils imports
    check_attempts,
    limiter_key,
    log_failed_attempt,
    failed_logins,
    failed_registrations,
)

# Define the blueprint
bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


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
@limiter.limit("5 per minute", key_func=limiter_key)
@limiter.limit("50 per hour", key_func=lambda: request.remote_addr or "unknown")  # Add hourly limit
def login():
    """Handle user login requests."""
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    form = LoginForm()
    if request.method == "POST":
        username = request.form.get("username", "").strip()

        if not check_attempts(username, failed_logins):
            logger.warning(
                "Rate limit exceeded for login attempts",
                extra={
                    "ip_address": request.remote_addr,
                    "route": request.path,
                    "username": username,
                },
            )
            form.errors['username'] = ['Too many login attempts. Please try again later.']
            return render_template("login.html", form=form)

        try:
            csrf_token = (
                request.form.get("csrf_token") or
                request.headers.get('X-CSRFToken') or
                request.headers.get('X-Csrf-Token')
            )
            try:
                validate_csrf(csrf_token)
            except Exception:
                logger.warning(
                    "CSRF token validation failed",
                    extra={"ip_address": request.remote_addr, "route": request.path},
                )
                form.errors['csrf_token'] = ['Invalid CSRF token. Please refresh the page and try again.']
                return render_template("login.html", form=form)

            if form.validate_on_submit():
                with db_session() as db:
                    user = (
                        db.execute(
                            text("SELECT * FROM users WHERE username = :username"),
                            {"username": username},
                        )
                        .mappings()
                        .first()
                    )

                    if not user or not user.get("password_hash"):
                        log_failed_attempt(username, failed_logins)
                        form.password.errors = ['Invalid username or password']
                        return render_template("login.html", form=form)

                    password_hash = user["password_hash"].decode("utf-8") if isinstance(user["password_hash"], bytes) else user["password_hash"]
                    if not password_hash or not check_password_hash(
                        pwhash=password_hash,
                        password=form.password.data.strip() if form.password.data else ""
                    ):

                        log_failed_attempt(username, failed_logins)
                        logger.warning(
                            "Invalid login attempt",
                            extra={
                                "ip_address": request.remote_addr,
                                "route": request.path,
                                "username": username,
                            },
                        )
                        form.password.errors = ['Invalid username or password']
                        return render_template("login.html", form=form)

                    user_obj = User(
                        user["id"], user["username"], user["email"], user["role"]
                    )
                    login_user(user_obj)
                    logger.info(
                        f"User {username} logged in successfully",
                        extra={
                            "ip_address": request.remote_addr,
                            "user_agent": request.headers.get('User-Agent'),
                            "route": request.path,
                            "user_id": user_obj.id,
                            "login_duration": (datetime.now() - session.get('login_time', datetime.now())).total_seconds(),
                        },
                    )
                    session['login_time'] = datetime.now()  # Track login time for session duration
                    return redirect(url_for("chat.chat_interface"))

            return render_template("login.html", form=form)

        except Exception as e:
            logger.error(
                f"Error during login process: {e}",
                exc_info=True,
                extra={
                    "ip_address": request.remote_addr,
                    "route": request.path,
                    "username": username,
                },
            )
            return handle_error(e, "Error during login process")

    return render_template("login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration requests."""
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    # Check if there are any existing users
    with db_session() as db:
        user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        is_first_user = user_count == 0

    form = RegistrationForm()
    if request.method == "POST":
        try:
            csrf_token = (
                request.form.get("csrf_token") or
                request.headers.get('X-CSRFToken') or
                request.headers.get('X-Csrf-Token')
            )
            try:
                validate_csrf(csrf_token)
            except (CSRFError, ValidationError) as e:
                logger.warning(
                    f"CSRF token validation failed during registration: {e}",
                    extra={"ip_address": request.remote_addr, "route": request.path},
                )
                form.errors['csrf_token'] = ['Invalid CSRF token. Please refresh the page and try again.']
                return render_template("register.html", form=form)

            ip = request.remote_addr or "unknown"
            if not check_attempts(ip, failed_registrations):
                logger.warning(
                    "Rate limit exceeded for registration attempts",
                    extra={"ip_address": ip, "route": request.path},
                )
                form.errors['username'] = ['Too many registration attempts. Please try again later.']
                return render_template("register.html", form=form)

            if form.validate_on_submit():
                start_time = datetime.now()
                username = form.username.data.strip() if form.username.data else ""
                email = form.email.data.lower().strip() if form.email.data else ""
                password = form.password.data if form.password.data else ""

                # Hash password before any database operations
                hashed_pw = generate_password_hash(password)
                if isinstance(hashed_pw, bytes):
                    hashed_pw = hashed_pw.decode("utf-8")

                with db_session() as db:
                    # Check for existing user
                    existing_user = (
                        db.execute(
                            text(
                                "SELECT id FROM users WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)"
                            ),
                            {"username": username, "email": email},
                        )
                        .mappings()
                        .first()
                    )

                    if existing_user:
                        log_failed_attempt(ip, failed_registrations)
                        logger.warning(
                            "Registration failed: username or email already exists",
                            extra={
                                "ip_address": ip,
                                "route": request.path,
                                "username": username,
                                "email": email,
                            },
                        )
                        form.email.errors = ['Username or email already exists']
                        return render_template("register.html", form=form)

                    # Create first user as admin
                    if is_first_user:
                        logger.info("Creating first admin user")
                        result = db.execute(
                            text(
                                """
                                INSERT INTO users (username, email, password_hash, role, is_verified)
                                VALUES (:username, :email, :password_hash, 'admin', TRUE)
                                RETURNING id, username, email, role
                            """
                            ),
                            {
                                "username": username,
                                "email": email,
                                "password_hash": hashed_pw,
                            },
                        ).fetchone()

                        # Create User object and log them in
                        user_obj = User(result[0], result[1], result[2], result[3])
                        login_user(user_obj)

                        logger.info(
                            "First admin user created successfully",
                            extra={
                                "ip_address": ip,
                                "route": request.path,
                                "email_hash": hashlib.sha256(email.encode()).hexdigest(),
                                "duration_ms": (datetime.now() - start_time).total_seconds() * 1000
                            }
                        )

                        return redirect(url_for('chat.chat_interface'))

                    # For non-first users, check username uniqueness
                    existing_username = db.execute(
                        text("SELECT id FROM users WHERE LOWER(username) = LOWER(:username)"),
                        {"username": username},
                    ).scalar()

                    if existing_username:
                        log_failed_attempt(ip, failed_registrations)
                        logger.warning(
                            "Registration failed: username already exists",
                            extra={
                                "ip_address": ip,
                                "route": request.path,
                                "username": username,
                            },
                        )
                        form.username.errors = ['This username is already taken']
                        return render_template("register.html", form=form)

                    # Create regular user
                    logger.info(
                        "Creating new regular user",
                        extra={
                            "username": username,
                            "email": email,
                        }
                    )
                    hashed_pw = generate_password_hash(password)
                    if isinstance(hashed_pw, bytes):
                        hashed_pw = hashed_pw.decode("utf-8")

                    result = db.execute(
                        text(
                            """
                            INSERT INTO users (username, email, password_hash, role, is_verified)
                            VALUES (:username, :email, :password_hash, 'user', TRUE)
                            RETURNING id, username, email, role
                        """
                        ),
                        {
                            "username": username,
                            "email": email,
                            "password_hash": hashed_pw,
                        },
                    ).fetchone()

                    # Create User object and log them in
                    user_obj = User(result[0], result[1], result[2], result[3])
                    login_user(user_obj)

                logger.info(
                    "User registration successful",
                    extra={
                        "ip_address": ip,
                        "route": request.path,
                        "email_hash": hashlib.sha256(email.encode()).hexdigest(),
                        "duration_ms": (datetime.now() - start_time).total_seconds() * 1000
                    }
                )

                return redirect(url_for('chat.chat_interface'))

            return render_template("register.html", form=form)

        except Exception as e:
            logger.error(
                f"Registration error: {e}",
                exc_info=True,
                extra={
                    "ip_address": request.remote_addr,
                    "route": request.path,
                    "username": form.username.data if form.username.data else None,
                    "email": form.email.data if form.email.data else None,
                },
            )
            form.errors['non_field_errors'] = ['An unexpected error occurred. Please try again.']
            return render_template("register.html", form=form)

    return render_template("register.html", form=form)


@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    """Handle forgot password requests."""
    form = ResetPasswordForm()  # Initialize form
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        try:
            if not validate_email(email):
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

            with db_session() as db:
                user = (
                    db.execute(
                        text("SELECT id, email FROM users WHERE email = :email"),
                        {"email": email},
                    )
                    .mappings()
                    .first()
                )

                if not user:
                    logger.info(
                        "Password reset requested for non-existent email",
                        extra={
                            "ip_address": request.remote_addr,
                            "route": request.path,
                            "email": email,
                        },
                    )
                    return (
                        jsonify(
                            {
                                "success": True,
                                "message": (
                                    "If an account exists with this email, "
                                    "you will receive password reset instructions."
                                ),
                            }
                        ),
                        200,
                    )

                reset_token = secrets.token_urlsafe(32)
                reset_token_hash = generate_password_hash(reset_token)

                db.execute(
                    text(
                        """
                        UPDATE users
                        SET reset_token_hash = :token_hash,
                            reset_token_expiry = NOW() + INTERVAL '1 hour'
                        WHERE email = :email
                    """
                    ),
                    {"token_hash": reset_token_hash, "email": email},
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
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": (
                                "If an account exists with this email, "
                                "you will receive password reset instructions."
                            ),
                        }
                    ),
                    200,
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

    return render_template("forgot_password.html", form=form)  # Pass form to template

@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token: str):
    """Handle password reset requests."""
    form = ResetPasswordForm()

    try:
        with db_session() as db:
            user = (
                db.execute(
                    text(
                        "SELECT * FROM users WHERE reset_token_expiry > NOW() AND reset_token_hash IS NOT NULL"
                    )
                )
                .mappings()
                .first()
            )

            if not user or not check_password_hash(
                user["reset_token_hash"], token
            ):
                logger.warning(
                    "Invalid or expired reset token used",
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
                hashed_password = generate_password_hash(form.password.data.strip() if form.password.data else "")
                if isinstance(hashed_password, bytes):
                    hashed_password = hashed_password.decode("utf-8")

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




@bp.route("/logout")
@login_required
def logout():
    """Handle user logout."""
    logger.info(
        "User logged out",
        extra={
            "user_id": current_user.id,
            "ip_address": request.remote_addr,
            "route": request.path,
            "session_duration": (datetime.now() - session.get('login_time', datetime.now())).total_seconds()
        }
    )
    logout_user()
    return redirect(url_for("auth.login"))
