"""
Authentication routes for the application.
"""

import logging
import uuid
from datetime import datetime, timedelta
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
    current_app,
)
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import text
from email_validator import validate_email, EmailNotValidError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from database import get_db
from models import User, Model
from decorators import admin_required
from forms import LoginForm, RegistrationForm, ResetPasswordForm, DefaultModelForm
from chat_utils import send_reset_email
from extensions import limiter, csrf

# Define the blueprint
bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# Track failed registration attempts
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
    # Schedule next clean-up
    current_app.logger.debug("Cleaning up failed registration attempts.")
    limiter_app = current_app.extensions.get("limiter")
    if limiter_app:
        limiter_app.logger.debug("Setting up periodic clean-up for failed registrations.")
    else:
        logger.debug("Limiter app not found.")

# Start the first clean-up
clean_failed_registrations()

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
    form = ResetPasswordForm()
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        try:
            # Validate email format
            valid = validate_email(email)
            email = valid.email
        except EmailNotValidError as e:
            logger.warning(f"Invalid email format provided: {email}")
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
                # Return a generic message to prevent email enumeration
                return jsonify({
                    "success": True,
                    "message": "If an account exists with this email, you will receive password reset instructions."
                }), 200

            # Generate and store reset token
            reset_token = str(uuid.uuid4())
            db.execute(
                text("""
                    UPDATE users
                    SET reset_token = :token,
                        reset_token_expiry = datetime('now', '+1 hour')
                    WHERE email = :email
                """),
                {"token": reset_token, "email": email}
            )
            db.commit()

            # Send reset email
            reset_url = url_for('auth.reset_password', token=reset_token, _external=True)
            send_reset_email(email, reset_url)

            logger.info("Password reset token generated for user: %s", user["id"])
            return jsonify({
                "success": True,
                "message": "If an account exists with this email, you will receive password reset instructions."
            }), 200

        except Exception as e:
            db.rollback()
            logger.exception("Error during password reset: %s", str(e))
            return jsonify({
                "success": False,
                "error": "An error occurred. Please try again later."
            }), 500

    # GET request - render template
    return render_template("forgot_password.html", form=form)

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

@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    """Handle user login requests."""
    if current_user.is_authenticated:
        logger.debug("User already authenticated; redirecting to chat interface.")
        return redirect(url_for("chat.chat_interface"))

    form = LoginForm()
    if request.method == "POST":
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

                # Check if user exists
                if not user:
                    logger.warning(f"Login attempt for non-existent username: {username}")
                    return jsonify({
                        "success": False,
                        "error": "Username not found"
                    }), 401

                # Check password
                if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                    logger.warning(f"Invalid password for username: {username}")
                    return jsonify({
                        "success": False,
                        "error": "Incorrect password"
                    }), 401

                # Successful login
                user_obj = User(
                    user["id"], user["username"], user["email"], user["role"]
                )
                session.clear()
                login_user(user_obj)
                logger.info(f"User {user['id']} logged in successfully.")
                return jsonify({"success": True, "message": "Login successful"}), 200

            except Exception as e:
                log_and_rollback(db, e, "Error during login process")
                return jsonify({
                    "success": False,
                    "error": "An unexpected error occurred. Please try again later."
                }), 500

        else:
            logger.debug(f"Form validation errors: {form.errors}")
            return jsonify({"success": False, "errors": form.errors}), 400

    # GET request - render template
    return render_template("login.html", form=form)

@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    """Handle user registration requests."""
    if current_user.is_authenticated:
        logger.debug("User already authenticated; redirecting to chat interface.")
        return redirect(url_for("chat.chat_interface"))

    form = RegistrationForm()
    if request.method == "POST":
        # Ensure IP address is not None
        ip = request.remote_addr or "unknown"
        logger.debug(f"Processing registration form from IP: {ip}")

        if not check_registration_attempts(ip):
            return jsonify({
                "success": False,
                "error": "Too many registration attempts. Please try again later."
            }), 429

        if form.validate_on_submit():
            # Safely handle potentially None values
            username = form.username.data.strip() if form.username.data else None
            email = form.email.data.lower().strip() if form.email.data else None
            password = form.password.data if form.password.data else None

            if not all([username, email, password]):
                return jsonify({
                    "success": False,
                    "error": "All fields are required"
                }), 400

            db = get_db()
            try:
                # Check for existing user
                existing_user = db.execute(
                    text("SELECT id FROM users WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)"),
                    {"username": username, "email": email}
                ).mappings().first()

                if existing_user:
                    logger.warning(f"Registration attempt failed: username/email exists (IP: {ip}).")
                    failed_registrations.setdefault(ip, []).append(datetime.now())
                    return jsonify({
                        "success": False,
                        "error": "Username or email already exists"
                    }), 400

                # Check if this is the first user
                user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
                is_first_user = user_count == 0

                # Create new user with admin role if first user
                role = 'admin' if is_first_user else 'user'
                hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
                db.execute(
                    text("INSERT INTO users (username, email, password_hash, role) VALUES (:username, :email, :password_hash, :role)"),
                    {"username": username, "email": email, "password_hash": hashed_pw, "role": role}
                )
                db.commit()

                # Create default model if no models exist
                model_count = db.execute(text("SELECT COUNT(*) FROM models")).scalar()
                if model_count == 0:
                    try:
                        Model.create_default_model()
                    except ValueError as e:
                        logger.error(f"Failed to create default model: {e}")
                        # Store registration data in session
                        session['registration_data'] = {
                            'username': username,
                            'email': email
                        }
                        # Return JSON response indicating the need to redirect
                        return jsonify({
                            "success": False,
                            "error": "Default model configuration is invalid",
                            "redirect": url_for("auth.edit_default_model")
                        }), 400

                # Load the user object and log the user in
                user_obj = User(
                    id=db.execute(text("SELECT id FROM users WHERE username = :username"), {"username": username}).scalar(),
                    username=username,
                    email=email,
                    role=role
                )
                session.clear()
                login_user(user_obj)

                logger.info(f"New user registered and logged in successfully: {username}")
                return jsonify({"success": True, "message": "Registration successful"}), 200

            except Exception as e:
                db.rollback()
                logger.exception("Error during registration.")
                return jsonify({
                    "success": False,
                    "error": "An error occurred during registration. Please try again."
                }), 500

        return jsonify({"success": False, "errors": form.errors}), 400

    # GET request - render template
    # Retrieve data from session if available
    registration_data = session.pop('registration_data', {})
    form = RegistrationForm(data=registration_data)
    return render_template("register.html", form=form)

@bp.route("/edit_default_model", methods=["GET", "POST"])
def edit_default_model():
    """Handle editing of the default model configuration during registration."""
    form = DefaultModelForm()
    registration_form = RegistrationForm()

    if request.method == "POST":
        if form.validate_on_submit():
            # Extract data from form
            default_model_data = {
                "name": form.name.data,
                "deployment_name": form.deployment_name.data,
                "description": form.description.data,
                "model_type": "azure",
                "api_endpoint": form.api_endpoint.data.rstrip('/'),
                "api_key": form.api_key.data.strip(),
                "temperature": form.temperature.data,
                "max_tokens": form.max_tokens.data,
                "max_completion_tokens": form.max_completion_tokens.data,
                "is_default": True,
                "requires_o1_handling": form.requires_o1_handling.data,
                "supports_streaming": form.supports_streaming.data,
                "api_version": form.api_version.data.strip(),
                "version": 1,
            }
            try:
                model_id = Model.create(default_model_data)
                logger.info(f"Default model created successfully with ID {model_id}")
                # After creating the default model, attempt to register the user again
                return redirect(url_for("auth.register"))
            except Exception as e:
                logger.error(f"Error creating default model: {e}")
                model_error = "Failed to create default model. Please check the configuration and try again."
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
    else:
        # GET request - render the form
        return render_template(
            "edit_default_model.html",
            form=form
        )

@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token: str):
    """Handle password reset requests."""
    form = ResetPasswordForm()
    db = get_db()

    try:
        user = db.execute(
            text("SELECT * FROM users WHERE reset_token = :token AND reset_token_expiry > datetime('now')"),
            {"token": token}
        ).mappings().first()

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

        # GET request - render the reset password form
        return render_template("reset_password.html", form=form, token=token)

    except Exception as e:
        logger.exception("Error during password reset.")
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred."
        }), 500

@bp.route("/logout")
@login_required
def logout():
    """Logs out the current user, clears the session, and redirects to the login page."""
    logger.info(f"User {current_user.id} logged out.")
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))