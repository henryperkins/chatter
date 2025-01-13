# auth_routes.py

from datetime import datetime, timedelta
import logging
import uuid
from threading import Timer
from typing import Union, Dict, List, Tuple

import bcrypt
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    Response as FlaskResponse,
)
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf.csrf import validate_csrf
from sqlalchemy import text
from werkzeug.wrappers import Response as WerkzeugResponse
from email_validator import validate_email, EmailNotValidError
from chat_utils import send_reset_email
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from database import get_db
from models import User
from decorators import admin_required
from forms import LoginForm, RegistrationForm, ResetPasswordForm
from extensions import limiter

# Define the blueprint
bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# Rate limiting for sensitive routes
limiter = Limiter(key_func=get_remote_address)

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
    Timer(900, clean_failed_registrations).start()  # Run every 15 minutes

# Start the first clean-up

@bp.route("/manage_users", methods=["GET"])
@login_required
@admin_required
def manage_users():
    """Render the manage users page for admin users."""
    return render_template("manage_users.html")
timer = Timer(900, clean_failed_registrations)
timer.start()

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
    """Handle user login requests. Validates credentials and logs the user in."""
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
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Username not found",
                            }
                        ),
                        401,
                    )

                # Check password
                if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                    logger.warning(f"Invalid password for username: {username}")
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Incorrect password",
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

                # Create new user
                hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
                db.execute(
                    text("INSERT INTO users (username, email, password_hash, role) VALUES (:username, :email, :password_hash, 'user')"),
                    {"username": username, "email": email, "password_hash": hashed_pw}
                )
                db.commit()
                logger.info(f"New user registered successfully: {username}")
                return jsonify({"success": True, "message": "Registration successful"}), 200

            except Exception as e:
                db.rollback()
                logger.error(f"Error during registration: {e}")
                return jsonify({
                    "success": False,
                    "error": "An error occurred during registration"
                }), 500

        return jsonify({"success": False, "errors": form.errors}), 400

    return render_template("register.html", form=form)

@bp.route("/logout")
@login_required
def logout():
    """Logs out the current user, clears the session, and redirects to the login page."""
    logger.info(f"User {current_user.id} logged out.")
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))

@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    """Handle forgot password requests. Validates email, generates reset token, and sends password reset email."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        try:
            # Validate email address
            validate_email(email, check_deliverability=False)
        except EmailNotValidError:
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
                    "error": "If an account exists with this email, you will receive password reset instructions."
                }), 200  # Return 200 to prevent email enumeration

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
            reset_url = url_for(
                'auth.reset_password',
                token=reset_token,
                _external=True
            )
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
    return render_template("forgot_password.html")

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

        logger.debug(f"Rendering reset password form for token: {token}")
        return render_template("reset_password.html", form=form)

    except Exception as e:
        logger.error(f"Error during password reset: {e}")
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred"
        }), 500
