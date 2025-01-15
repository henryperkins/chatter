"""
Authentication routes for the application.
"""

import logging
import os
import secrets
import bcrypt
from flask import (
    Blueprint,
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
from forms import DefaultModelForm, LoginForm, RegistrationForm, ResetPasswordForm
from models import Model, User
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

                    if not user or not bcrypt.checkpw(
                        form.password.data.strip().encode("utf-8"),
                        user["password_hash"],
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
                        form.password.errors.append('Invalid username or password')
                        return render_template("login.html", form=form)

                    user_obj = User(
                        user["id"], user["username"], user["email"], user["role"]
                    )
                    login_user(user_obj)
                    logger.info(
                        f"User {username} logged in successfully",
                        extra={
                            "ip_address": request.remote_addr,
                            "route": request.path,
                            "user_id": user_obj.id,
                        },
                    )
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
                username = form.username.data.strip()
                email = form.email.data.lower().strip()
                password = form.password.data

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
                        form.email.errors.append('Username or email already exists')
                        return render_template("register.html", form=form)

                    # Check if this will be the first user
                    user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
                    is_first_user = user_count == 0

                    if is_first_user:
                        model_count = db.execute(
                            text("SELECT COUNT(*) FROM models")
                        ).scalar()
                        if model_count == 0:
                            session["registration_data"] = {
                                "username": username,
                                "email": email,
                                "password": password,
                            }
                            logger.info(
                                "Redirecting first user to default model configuration",
                                extra={
                                    "ip_address": ip,
                                    "route": request.path,
                                    "username": username,
                                    "email": email,
                                },
                            )
                            return redirect(url_for("auth.edit_default_model"))

                    # Create regular user
                    cost_factor = int(os.environ.get("BCRYPT_COST_FACTOR", 12))
                    hashed_pw = bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt(rounds=cost_factor)
                    )

                    db.execute(
                        text(
                            """
                            INSERT INTO users (username, email, password_hash, role, is_verified)
                            VALUES (:username, :email, :password_hash, :role, 1)
                        """
                        ),
                        {
                            "username": username,
                            "email": email,
                            "password_hash": hashed_pw,
                            "role": "user",
                        },
                    )

                logger.info(
                    f"User {username} registered successfully",
                    extra={"ip_address": ip, "route": request.path, "email": email},
                )
                return redirect(url_for('auth.login'))

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
                reset_token_hash = bcrypt.hashpw(
                    reset_token.encode("utf-8"), bcrypt.gensalt(rounds=12)
                )

                db.execute(
                    text(
                        """
                        UPDATE users
                        SET reset_token_hash = :token_hash,
                            reset_token_expiry = datetime('now', '+1 hour')
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

    return render_template("forgot_password.html")

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
                        "SELECT * FROM users WHERE reset_token_expiry > datetime('now') AND reset_token_hash IS NOT NULL"
                    )
                )
                .mappings()
                .first()
            )

            if not user or not bcrypt.checkpw(
                token.encode("utf-8"), user["reset_token_hash"]
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
                hashed_password = bcrypt.hashpw(
                    form.password.data.strip().encode("utf-8"),
                    bcrypt.gensalt(rounds=12),
                )

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


@bp.route("/edit_default_model", methods=["GET", "POST"])
def edit_default_model():
    """Handle editing of the default model configuration."""
    form = DefaultModelForm()
    registration_data = session.get("registration_data", {})
    is_existing_admin = registration_data.get("password") is None

    if not registration_data and not is_existing_admin:
        return redirect(url_for("auth.register"))

    if request.method == "POST" and form.validate_on_submit():
        try:
            if not Config.ENCRYPTION_KEY:
                raise ValueError("ENCRYPTION_KEY environment variable must be set")

            model_data = {
                "name": form.name.data,
                "deployment_name": form.deployment_name.data,
                "description": form.description.data,
                "model_type": form.model_type.data,
                "api_endpoint": form.api_endpoint.data,
                "api_key": form.api_key.data,
                "temperature": form.temperature.data,
                "max_tokens": form.max_tokens.data,
                "max_completion_tokens": form.max_completion_tokens.data,
                "is_default": True,
                "requires_o1_handling": form.requires_o1_handling.data,
                "supports_streaming": form.supports_streaming.data,
                "api_version": form.api_version.data,
                "version": 1,
            }

            with db_session() as db:
                default_model = (
                    db.execute(text("SELECT id FROM models WHERE is_default = 1"))
                    .mappings()
                    .first()
                )

                if default_model:
                    Model.update(default_model["id"], model_data)
                else:
                    model_id = Model.create(model_data)
                    try:
                        created_model = Model.get_by_id(model_id)
                        if not created_model:
                            raise ValueError("Failed to retrieve the created model.")
                    except Exception as e:
                        raise ValueError(f"Failed to create and validate model: {str(e)}")

                if not is_existing_admin:
                    cost_factor = int(os.environ.get("BCRYPT_COST_FACTOR", 12))
                    hashed_pw = bcrypt.hashpw(
                        registration_data["password"].encode("utf-8"),
                        bcrypt.gensalt(rounds=cost_factor),
                    )

                    db.execute(
                        text(
                            """
                            INSERT INTO users (username, email, password_hash, role, is_verified)
                            VALUES (:username, :email, :password_hash, 'admin', 1)
                        """
                        ),
                        {
                            "username": registration_data["username"],
                            "email": registration_data["email"],
                            "password_hash": hashed_pw,
                        },
                    )

                session.pop("registration_data", None)
                logger.info(
                    "Default model edited successfully and admin user created",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "username": registration_data.get("username"),
                        "email": registration_data.get("email"),
                    },
                )

                # Log in the new admin user
                with db_session() as db:
                    user = (
                        db.execute(
                            text("SELECT * FROM users WHERE username = :username"),
                            {"username": registration_data["username"]},
                        )
                        .mappings()
                        .first()
                    )
                user_obj = User(
                    user["id"], user["username"], user["email"], user["role"]
                )
                login_user(user_obj)

                return redirect(url_for("chat.chat_interface"))

        except Exception as e:
            logger.error(
                f"Error handling model configuration: {e}",
                exc_info=True,
                extra={"ip_address": request.remote_addr, "route": request.path},
            )
            return render_template(
                "edit_default_model.html",
                form=form,
                model_error=str(e),
                is_existing_admin=is_existing_admin,
            )

    model_error = None
    if form.errors:
        model_error = "Please correct the errors in the form."
    elif not Config.ENCRYPTION_KEY:
        model_error = "ENCRYPTION_KEY environment variable must be set"

    try:
        if not form.is_submitted():
            with db_session() as db:
                default_model = (
                    db.execute(text("SELECT * FROM models WHERE is_default = 1"))
                    .mappings()
                    .first()
                )

            if default_model:
                for field in form._fields:
                    if field in default_model:
                        getattr(form, field).data = default_model[field]
            else:
                form.name.data = Config.DEFAULT_MODEL_NAME
                form.deployment_name.data = Config.DEFAULT_DEPLOYMENT_NAME
                form.description.data = Config.DEFAULT_MODEL_DESCRIPTION
                form.api_endpoint.data = Config.DEFAULT_API_ENDPOINT
                form.api_key.data = Config.AZURE_API_KEY
                form.temperature.data = Config.DEFAULT_TEMPERATURE
                form.max_tokens.data = Config.DEFAULT_MAX_TOKENS
                form.max_completion_tokens.data = Config.DEFAULT_MAX_COMPLETION_TOKENS
                form.requires_o1_handling.data = Config.DEFAULT_REQUIRES_O1_HANDLING
                form.supports_streaming.data = Config.DEFAULT_SUPPORTS_STREAMING
                form.api_version.data = Config.DEFAULT_API_VERSION
                form.model_type.data = "o1-preview"
    except Exception as e:
        logger.error(
            f"Error loading default model data: {e}",
            exc_info=True,
            extra={"ip_address": request.remote_addr, "route": request.path},
        )
        model_error = "Error loading model configuration"

    return render_template(
        "edit_default_model.html",
        form=form,
        model_error=model_error,
        is_existing_admin=is_existing_admin,
    )


@bp.route("/logout")
@login_required
def logout():
    """Handle user logout."""
    logger.info(
        f"User {current_user.id} logged out",
        extra={"ip_address": request.remote_addr, "route": request.path},
    )
    logout_user()
    return redirect(url_for("auth.login"))
