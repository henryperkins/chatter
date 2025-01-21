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
from forms import DefaultModelForm, LoginForm, RegistrationForm, ResetPasswordForm
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

                    # Store registration data in session if first user
                    if is_first_user:
                        session["registration_data"] = {
                            "username": username,
                            "email": email,
                            "password": password,
                        }
                        logger.info("First user registration - redirecting to model config")
                        return redirect(url_for("auth.edit_default_model"))

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


@bp.route("/edit_default_model", methods=["GET", "POST"])
def edit_default_model():
    """Handle editing of the default model configuration."""
    # Debugging logs to verify application context and initialization
    from flask import current_app
    from database import is_initialized
    if not current_app:
        logger.error("Flask application context is not active.")
    logger.debug(f"Database initialized: {is_initialized()}")
    # Define valid model types
    MODEL_TYPES = [
        ('azure', 'Azure OpenAI'),
        ('o1-preview', 'O1 Preview'),
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic')
    ]

    form = DefaultModelForm()
    form.model_type.choices = MODEL_TYPES  # Set choices for model_type field
    
    registration_data = session.get("registration_data", {})
    is_existing_admin = registration_data.get("password") is None

    if not registration_data and not is_existing_admin:
        return redirect(url_for("auth.register"))

    if request.method == "POST":
        if not form.validate_on_submit():
            logger.warning(
                "Form validation failed",
                extra={
                    "errors": form.errors,
                    "user_id": current_user.id if current_user.is_authenticated else None
                }
            )
            return render_template(
                "edit_default_model.html",
                form=form,
                model_error="Please correct the form errors.",
                is_existing_admin=is_existing_admin,
                allow_skip=True
            )

        try:
            if not Config.ENCRYPTION_KEY:
                logger.warning("ENCRYPTION_KEY environment variable not set")

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
                    db.execute(text("SELECT id FROM models WHERE is_default = TRUE"))
                    .mappings()
                    .first()
                )

                if default_model:
                    Model.update(default_model["id"], model_data)
                else:
                    model_id = Model.create(model_data)
                    if model_id is None:
                        raise ValueError("Failed to create model")
                    try:
                        created_model = Model.get_by_id(model_id)
                        if not created_model:
                            raise ValueError("Failed to retrieve the created model.")
                    except Exception as e:
                        raise ValueError(f"Failed to create and validate model: {str(e)}")

                if not is_existing_admin:
                    hashed_pw = generate_password_hash(registration_data["password"])
                    if isinstance(hashed_pw, bytes):
                        hashed_pw = hashed_pw.decode("utf-8")

                    db.execute(
                        text(
                            """
                            INSERT INTO users (username, email, password_hash, role, is_verified)
                            VALUES (:username, :email, :password_hash, 'admin', TRUE)
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
                "Error handling model configuration: %s",
                str(e),
                exc_info=True,
                extra={
                    "ip_address": request.remote_addr,
                    "route": request.path,
                    "user_id": current_user.id if current_user.is_authenticated else None
                }
            )
            error_message = "Failed to save model configuration. "
            if "duplicate key value violates unique constraint" in str(e):
                error_message += "A model with these details already exists."
            else:
                error_message += "Please verify your settings and try again."
            
            return render_template(
                "edit_default_model.html",
                form=form,
                model_error=error_message,
                is_existing_admin=is_existing_admin,
                allow_skip=True
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
                    db.execute(text("SELECT * FROM models WHERE is_default = TRUE"))
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
@bp.route("/skip_model_config", methods=["POST"])
@login_required
def skip_model_config():
    """Handle skipping the initial model configuration."""
    try:
        # Verify CSRF token
        csrf_token = request.form.get("csrf_token")
        try:
            validate_csrf(csrf_token)
        except Exception:
            logger.warning("CSRF validation failed during skip_model_config")
            return redirect(url_for("auth.edit_default_model"))

        # Clear any pending registration data
        session.pop("registration_data", None)
        
        # Log the skip
        logger.info(
            "Model configuration skipped by user",
            extra={
                "user_id": current_user.id,
                "username": current_user.username
            }
        )
        
        # Add flash message
        flash("Model configuration skipped. You can configure it later through the admin panel.", "warning")
        
        # Redirect to chat interface
        return redirect(url_for("chat.chat_interface"))
        
    except Exception as e:
        logger.error("Error during skip_model_config: %s", str(e), exc_info=True)
        flash("An error occurred while skipping model configuration.", "error")
        return redirect(url_for("auth.edit_default_model"))
