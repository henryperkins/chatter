"""
Authentication routes for the application.
"""

from datetime import datetime, timedelta
import logging
import uuid
from typing import Dict, List

import bcrypt
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
)
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import text
from email_validator import validate_email, EmailNotValidError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.util import get_remote_address
import secrets
from chat_utils import send_verification_email
from flask_wtf.csrf import validate_csrf, CSRFError
import os

from database import get_db
from models import User, Model
from decorators import admin_required
from forms import LoginForm, RegistrationForm, ResetPasswordForm, DefaultModelForm
from chat_utils import send_reset_email
from extensions import limiter

# Define the blueprint
bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# Track failed login and registration attempts
failed_logins: Dict[str, List[datetime]] = {}
failed_registrations: Dict[str, List[datetime]] = {}

def clean_failed_registrations():
    """Cleans up old failed registration attempts from the tracking dictionary."""
    now = datetime.now()
    to_delete = []
    for ip, timestamps in failed_registrations.items():
        # Remove timestamps older than 15 minutes
        failed_registrations[ip] = [
            ts for ts in timestamps if now - ts < timedelta(minutes=15)
        ]
        if not failed_registrations[ip]:
            to_delete.append(ip)
    # Delete IPs with no recent attempts
    for ip in to_delete:
        del failed_registrations[ip]


@bp.route("/manage_users", methods=["GET"])
@login_required
@admin_required
def manage_users():
    """Render the manage users page."""
    return render_template("manage_users.html")

@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    """Handle forgot password requests."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        if not validate_email(email):
            logger.warning("Invalid email format provided")
            return jsonify({
                "success": False,
                "error": "Please provide a valid email address."
            }), 400

        db = get_db()
        try:
            # Query for existing user
            user = db.execute(
                text("SELECT id, email FROM users WHERE email = :email"),
                {"email": email}
            ).mappings().first()

            if not user:
                logger.info("Password reset attempted for non-existent email: %s", email)
                return jsonify({
                    "success": False,
                    "error": "If an account exists with this email, "
                            "you will receive password reset instructions."
                }), 200  # Return 200 to prevent email enumeration

            # Generate and store reset token
            reset_token = secrets.token_urlsafe(32)
            reset_token_hash = bcrypt.hashpw(reset_token.encode("utf-8"), bcrypt.gensalt(rounds=12))
            db.execute(
                text("""
                    UPDATE users
                    SET reset_token_hash = :token_hash,
                        reset_token_expiry = datetime('now', '+1 hour')
                    WHERE email = :email
                """),
                {"token_hash": reset_token_hash, "email": email}
            )
            db.commit()

            # Send reset email
            reset_url = url_for(
                'auth.reset_password',
                token=reset_token,
                _external=True
            )
            send_reset_email(email, reset_url)

            logger.info("Password reset token generated for user: %s", user["id"])
            return jsonify({
                "success": True,
                "message": "If an account exists with this email, "
                          "you will receive password reset instructions."
            }), 200

        except Exception as e:
            db.rollback()
            logger.exception("Error during password reset: %s", str(e))
            return jsonify({
                "success": False,
                "error": "An error occurred. Please try again later."
            }), 500

    # GET request - render template
    return render_template("forgot_password.html")

def log_and_rollback(db, exception, user_message="An unexpected error occurred"):
    """Helper function to log an error and rollback a database transaction."""
    db.rollback()
    logger.error(f"{user_message}: {exception}", exc_info=True)
    raise exception

def check_registration_attempts(ip: str) -> bool:
    """Checks whether an IP address has exceeded the allowed number of registration attempts."""
    now = datetime.now()
    if ip in failed_registrations:
        # Clean up old attempts
        failed_registrations[ip] = [
            timestamp
            for timestamp in failed_registrations[ip]
            if now - timestamp < timedelta(minutes=15)
        ]
        if len(failed_registrations[ip]) >= 5:
            logger.warning(f"IP {ip} has exceeded registration attempts with {len(failed_registrations[ip])} attempts.")
            return False
    return True

def check_login_attempts(identifier: str) -> bool:
    """Check if the identifier (username or IP) has exceeded allowed login attempts."""
    now = datetime.now()
    attempts = failed_logins.get(identifier, [])
    # Remove attempts older than 15 minutes
    attempts = [t for t in attempts if now - t < timedelta(minutes=15)]
    failed_logins[identifier] = attempts
    if len(attempts) >= 5:
        return False
    return True

def limiter_key():
    """Rate limit key based on IP and username."""
    username = request.form.get("username", "")
    return f"{get_remote_address()}:{username}"

@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", key_func=limiter_key)
def login():
    """Handle user login requests. Validates credentials and logs the user in."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if not check_login_attempts(username):
            return jsonify({
                "success": False,
                "error": "Too many login attempts. Please try again later."
            }), 429
    if current_user.is_authenticated:
        logger.debug("User already authenticated; redirecting to chat interface.")
        return redirect(url_for("chat.chat_interface"))

    form = LoginForm()
    if request.method == "POST":
        try:
            csrf_token = request.form.get('csrf_token')
            if not csrf_token:
                raise CSRFError('Missing CSRF token.')
            validate_csrf(csrf_token)
        except CSRFError as e:
            logger.error(f"CSRF validation failed during login: {e.description if hasattr(e, 'description') else str(e)}")
            return jsonify({"success": False, "error": "Invalid CSRF token."}), 400

        logger.debug("Processing login form submission.")
        if form.validate_on_submit():
            username = form.username.data.strip()
            password = form.password.data.strip()
            db = get_db()

            try:
                user = (
                    db.execute(
                        text("SELECT * FROM users WHERE username = :username"),
                        {"username": username},
                    )
                    .mappings()
                    .first()
                )
                logger.debug(f"Database query result for username '{username}': {user}")

                # Check if user exists and password matches
                if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                    failed_logins.setdefault(username, []).append(datetime.now())
                    logger.warning(f"Failed login attempt for username: {username}")
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Invalid username or password",
                            }
                        ),
                        401,
                    )

                # Successful login
                user_obj = User(
                    user["id"], user["username"], user["email"], user["role"]
                )
                session.clear()
                login_user(user_obj)
                logger.info(f"User {user.id} logged in successfully.")
                return jsonify({"success": True, "message": "Login successful"}), 200

            except Exception as e:
                log_and_rollback(db, e, "Error during login process")
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "An unexpected error occurred. Please try again later.",
                        }
                    ),
                    500,
                )

        else:
            logger.debug(f"Form validation errors: {form.errors}")
            return jsonify({"success": False, "errors": form.errors}), 400

    logger.debug("Rendering login form.")
    return render_template("login.html", form=form)

@bp.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration requests."""
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    form = RegistrationForm()
    if request.method == "POST":
        try:
            csrf_token = request.form.get('csrf_token')
            if not csrf_token:
                raise CSRFError('Missing CSRF token.')
            validate_csrf(csrf_token)
        except CSRFError as e:
            logger.error(f"CSRF validation failed during registration: {e.description if hasattr(e, 'description') else str(e)}")
            return jsonify({"success": False, "error": "Invalid CSRF token."}), 400

        clean_failed_registrations()
        ip = request.remote_addr or "unknown"
        
        if not check_registration_attempts(ip):
            return jsonify({
                "success": False,
                "error": "Too many registration attempts. Please try again later."
            }), 429

        logger.debug(f"Registration form data: {request.form}")


        if form.validate_on_submit():
            logger.debug("Registration form validated successfully")
            username = form.username.data.strip()
            email = form.email.data.lower().strip()
            password = form.password.data

            db = get_db()
            logger.debug(f"Creating new user: {username}, {email}")
            try:
                # Check for existing user
                existing_user = db.execute(
                    text("SELECT id FROM users WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)"),
                    {"username": username, "email": email}
                ).mappings().first()

                if existing_user:
                    failed_registrations.setdefault(ip, []).append(datetime.now())
                    return jsonify({
                        "success": False,
                        "error": "Username or email already exists"
                    }), 400

                # Create new user
                user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
                role = 'admin' if user_count == 0 else 'user'
                
                cost_factor = int(os.environ.get("BCRYPT_COST_FACTOR", 12))
                hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=cost_factor))
                verification_token = secrets.token_urlsafe(32)
                
                db.execute(
                    text("""
                        INSERT INTO users (username, email, password_hash, role, email_verification_token, is_verified)
                        VALUES (:username, :email, :password_hash, :role, :verification_token, 0)
                    """),
                    {
                        "username": username,
                        "email": email,
                        "password_hash": hashed_pw,
                        "role": role,
                        "verification_token": verification_token
                    }
                )
                
                # Create default model if none exists
                model_count = db.execute(text("SELECT COUNT(*) FROM models")).scalar()
                if model_count == 0:
                    try:
                        Model.create_default_model()
                    except ValueError as e:
                        logger.error(f"Failed to create default model: {e}")
                        return render_template(
                            "register.html",
                            form=form,
                            model_error=str(e)
                        )

                db.commit()
                # Placeholder: Skip email verification
                logger.warning("Email verification is currently disabled. All users are automatically verified.")
                db.execute(
                    text("""
                        UPDATE users
                        SET is_verified = 1, email_verification_token = NULL
                        WHERE email = :email
                    """),
                    {"email": email}
                )
                db.commit()  # Commit the verification status update
                logger.info(f"New user registered: {username}")
                return jsonify({"success": True, "message": "Registration successful"}), 200

            except Exception as e:
                db.rollback()
                logger.error(f"Registration error: {e}", exc_info=True)
                logger.debug(f"Failed registration data - Username: {username}, Email: {email}")
                return jsonify({
                    "success": False,
                    "error": "An error occurred during registration. Please try again."
                }), 500

        logger.debug(f"Form validation failed: {form.errors}")
        return jsonify({
            "success": False,
            "errors": form.errors,
            "error": "Please correct the errors in the form."
        }), 400

    return render_template("register.html", form=form)
@bp.route("/edit_default_model", methods=["GET", "POST"])
def edit_default_model():
    """Handle editing of the default model configuration during registration."""
    form = DefaultModelForm()
    registration_form = RegistrationForm()

    if request.method == "POST" and form.validate_on_submit():
        # Extract data from form
        default_model_data = {
            "name": form.name.data,
            "deployment_name": form.deployment_name.data,
            "description": form.description.data,
            "model_type": "azure",
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
        try:
            model_id = Model.create(default_model_data)
            logger.info(f"Default model created successfully with ID {model_id}")
            # After creating the default model, attempt to register the user again
            return redirect(url_for("auth.register"))
        except Exception as e:
            logger.error(f"Error creating default model: {e}")
            model_error = f"Error creating default model: {e}"
            return render_template(
                "edit_default_model.html",
                form=form,
                registration_form=registration_form,
                model_error=model_error
            )
    else:
        model_error = "Please correct the errors in the form."
        return render_template(
            "edit_default_model.html",
            form=form,
            registration_form=registration_form,
            model_error=model_error
        )

@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token: str):
    """Handle password reset requests."""
    form = ResetPasswordForm()
    db = get_db()

    try:
        user = db.execute(
            text("SELECT * FROM users WHERE reset_token_expiry > datetime('now') AND reset_token_hash IS NOT NULL"),
        ).mappings().first()

        if not user or not bcrypt.checkpw(token.encode("utf-8"), user["reset_token_hash"]):
            logger.warning("Invalid or expired reset token used.")
            return jsonify({"success": False, "error": "Invalid or expired reset token."}), 400

        if not user or not bcrypt.checkpw(token.encode("utf-8"), user["reset_token_hash"]):
            logger.warning("Invalid or expired reset token used.")
            return jsonify({"success": False, "error": "Invalid or expired reset token."}), 400

        if not user:
            logger.warning(f"Invalid or expired reset token used: {token}")
            return jsonify({"success": False, "error": "Invalid or expired reset token."}), 400

        if request.method == "POST" and form.validate_on_submit():
            password = form.password.data.strip()
            hashed_password = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(rounds=12)
            )

            try:
                db.execute(
                    text("UPDATE users SET password_hash = :password_hash, reset_token = NULL, reset_token_expiry = NULL WHERE id = :user_id"),
                    {"password_hash": hashed_password, "user_id": user["id"]}
                )
                db.commit()
                logger.info(f"Password reset successfully for user ID {user['id']}.")
                return jsonify({
                    "success": True,
                    "message": "Your password has been reset successfully."
                }), 200

            except Exception as e:
                return log_and_rollback(db, e, "Error during password reset")

        elif request.method == "POST":
            logger.debug(f"Form validation errors during password reset: {form.errors}")
            return jsonify({"success": False, "errors": form.errors}), 400

        logger.debug(f"Rendering reset password form for token: {token}")
        return render_template("reset_password.html", form=form)

    except Exception as e:
        logger.error(f"Error during password reset: {e}")
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred"
        }), 500
@bp.route("/verify_email/<token>", methods=["GET"])
def verify_email(token: str):
    """Verify the user's email address."""
    db = get_db()
    try:
        user = db.execute(
            text("SELECT id FROM users WHERE email_verification_token = :token"),
            {"token": token}
        ).mappings().first()

        if not user:
            return jsonify({"success": False, "error": "Invalid or expired verification token."}), 400

        db.execute(
            text("UPDATE users SET is_verified = 1, email_verification_token = NULL WHERE id = :user_id"),
            {"user_id": user["id"]}
        )
        db.commit()
        return jsonify({"success": True, "message": "Email verified successfully."}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying email: {e}")
        return jsonify({"success": False, "error": "An error occurred during email verification."}), 500
