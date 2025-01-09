# auth_routes.py

from datetime import datetime, timedelta
import logging
import bcrypt
import uuid
from typing import Dict, List
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, jsonify,
    Response
)
from flask_login import login_user, logout_user, current_user, login_required
from database import get_db
from sqlalchemy import text
from models import User
from decorators import admin_required
from forms import LoginForm, RegistrationForm, ResetPasswordForm
from extensions import limiter

# Define the blueprint
bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# Track failed registration attempts
failed_registrations: Dict[str, List[datetime]] = {}


def log_and_rollback(db, exception, user_message="An unexpected error occurred"):
    """
    Helper function to log an error and rollback a database transaction.
    
    Args:
        db: Database connection object.
        exception: Exception instance to log.
        user_message: Custom error message for the log.
    """
    db.rollback()
    logger.error(f"{user_message}: {exception}", exc_info=True)


def check_registration_attempts(ip: str) -> bool:
    """
    Checks whether an IP address has exceeded the allowed number of registration attempts.
    
    Args:
        ip (str): The client's IP address.

    Returns:
        bool: True if the IP is allowed to register, False otherwise.
    """
    now = datetime.now()
    if ip in failed_registrations:
        # Clean up old attempts
        failed_registrations[ip] = [
            timestamp for timestamp in failed_registrations[ip]
            if now - timestamp < timedelta(minutes=15)
        ]
        if len(failed_registrations[ip]) >= 5:
            logger.warning(f"IP {ip} has exceeded registration attempts.")
            return False
    return True


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5/minute")
def login():
    """
    Handle user login requests. Validates credentials and logs the user in.
    
    Returns:
        Response: JSON success or error message, or renders the login form.
    """
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
                user = db.execute(
                    text("SELECT * FROM users WHERE username = :username"),
                    {"username": username}
                ).mappings().first()
                logger.debug(f"Database query result for username '{username}': {user}")

                # Check if user exists
                if not user:
                    attempts_remaining = limiter.get_view_rate_limit()[1] - limiter.get_view_rate_limit()[0]
                    logger.warning(f"Login attempt for non-existent username: {username}")
                    return jsonify({
                        "success": False,
                        "error": "Username not found",
                        "attempts_remaining": attempts_remaining
                    }), 401

                # Check password
                if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                    attempts_remaining = limiter.get_view_rate_limit()[1] - limiter.get_view_rate_limit()[0]
                    logger.warning(f"Invalid password for username: {username}")
                    return jsonify({
                        "success": False,
                        "error": f"Incorrect password. {attempts_remaining} attempts remaining",
                        "attempts_remaining": attempts_remaining
                    }), 401

                # Successful login
                user_obj = User(user["id"], user["username"], user["email"], user["role"])
                session.clear()
                login_user(user_obj)
                logger.info(f"User {user.id} logged in successfully.")
                return jsonify({"success": True, "message": "Login successful"}), 200

            except Exception as e:
                log_and_rollback(db, e, "Error during login process")
                return jsonify({"success": False, "error": "An unexpected error occurred. Please try again later."}), 500

        else:
            logger.debug(f"Form validation errors: {form.errors}")
            return jsonify({"success": False, "errors": form.errors}), 400

    logger.debug("Rendering login form.")
    return render_template("login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register() -> Response:
    """
    Handle user registration requests. Validates input, creates an account, and prevents abuse.
    
    Returns:
        Response: JSON success or error message, or renders the registration form.
    """
    if current_user.is_authenticated:
        logger.debug("User already authenticated; redirecting to chat interface.")
        return redirect(url_for("chat.chat_interface"))

    form = RegistrationForm()
    if request.method == "POST":
        ip = request.remote_addr
        logger.debug(f"Processing registration form from IP: {ip}")

        if not check_registration_attempts(ip):
            return jsonify({"success": False, "error": "Too many registration attempts. Please try again later."}), 429

        if form.validate_on_submit():
            username = form.username.data.strip()
            email = form.email.data.lower().strip()
            password = form.password.data
            db = get_db()

            try:
                existing_user = db.execute(
                    text("SELECT id FROM users WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)"),
                    {"username": username, "email": email}
                ).mappings().first()

                if existing_user:
                    logger.warning(f"Registration attempt failed: username/email exists (IP: {ip}).")
                    failed_registrations.setdefault(ip, []).append(datetime.now())
                    return jsonify({"success": False, "error": "Username or email already exists"}), 400

                hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
                result = db.execute(
                    text("""
                        INSERT INTO users (username, email, password_hash, role)
                        VALUES (:username, :email, :password_hash, :role)
                        RETURNING id
                    """),
                    {
                        "username": username,
                        "email": email,
                        "password_hash": hashed_password,
                        "role": "user"
                    }
                )
                user_id = result.scalar()
                db.commit()
                logger.info(f"User {username} registered successfully.")

                # Create user object and log them in
                user_obj = User(user_id, username, email, "user")
                login_user(user_obj)

                return jsonify({
                    "success": True,
                    "message": "Registration successful!",
                    "redirect": url_for("chat.chat_interface")
                }), 200

            except Exception as e:
                log_and_rollback(db, e, "Database error during registration")
                return jsonify({"success": False, "error": "Registration failed due to database error"}), 500

        else:
            logger.debug(f"Form validation errors: {form.errors}")
            return jsonify({"success": False, "errors": form.errors}), 400

    logger.debug("Rendering registration form.")
    return render_template("register.html", form=form)


@bp.route("/logout")
@login_required
def logout() -> Response:
    """
    Logs out the current user, clears the session, and redirects to the login page.
    
    Returns:
        Response: Redirect to login page.
    """
    logger.info(f"User {current_user.id} logged out.")
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password() -> Response:
    """
    Handle forgot password requests. Sends a password reset token to the user's email.

    Returns:
        Response: JSON success or error message, or renders the forgot password form.
    """
    if request.method == "POST":
        email = request.form.get("email").strip()

        if not email:
            return jsonify({"success": False, "error": "Email is required."}), 400

        db = get_db()
        try:
            user = db.execute(
                text("SELECT * FROM users WHERE email = :email"),
                {"email": email}
            ).mappings().first()

            if not user:
                logger.warning(f"Password reset requested for non-existent email: {email}")
                return jsonify({"success": False, "error": "No account found with that email address."}), 404

            reset_token = str(uuid.uuid4())
            db.execute(
                text("UPDATE users SET reset_token = :token, reset_token_expiry = datetime('now', '+1 hour') WHERE email = :email"),
                {"token": reset_token, "email": email}
            )
            db.commit()
            logger.info(f"Password reset token generated for email: {email}")
            return jsonify({"success": True, "message": "A password reset link has been sent to your email."}), 200

        except Exception as e:
            log_and_rollback(db, e, "Error during password reset request")
            return jsonify({"success": False, "error": "Failed to process password reset"}), 500

    return render_template("forgot_password.html")


@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token):
    """
    Handle password reset requests using a valid token.
    
    Args:
        token (str): The password reset token.

    Returns:
        Response: JSON success or error message, or renders the reset password form.
    """
    form = ResetPasswordForm()
    db = get_db()

    # Validate the token
    try:
        user = db.execute(
            text("SELECT * FROM users WHERE reset_token = :token AND reset_token_expiry > datetime('now')"),
            {"token": token}
        ).mappings().first()
    except Exception as e:
        logger.error(f"Error validating reset token: {e}")
        return jsonify({"success": False, "error": "An unexpected error occurred. Please try again later."}), 500

    if not user:
        logger.warning(f"Invalid or expired reset token used: {token}")
        return jsonify({"success": False, "error": "Invalid or expired reset token."}), 400

    if request.method == "POST" and form.validate_on_submit():
        password = form.password.data.strip()
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))

        try:
            db.execute(
                text("UPDATE users SET password_hash = :password_hash, reset_token = NULL, reset_token_expiry = NULL WHERE id = :user_id"),
                {
                    "password_hash": hashed_password,
                    "user_id": user["id"]
                }
            )
            db.commit()
            logger.info(f"Password reset successfully for user ID {user.id}.")
            return jsonify({"success": True, "message": "Your password has been reset successfully."}), 200
        except Exception as e:
            log_and_rollback(db, e, "Error during password reset")
            return jsonify({"success": False, "error": "Failed to reset password. Please try again later."}), 500

    elif request.method == "POST":
        logger.debug(f"Form validation errors during password reset: {form.errors}")
        return jsonify({"success": False, "errors": form.errors}), 400

    logger.debug(f"Rendering reset password form for token: {token}")
    return render_template("reset_password.html", form=form)


@bp.route("/manage-users")
@login_required
@admin_required
def manage_users() -> Response:
    """
    Display a list of all users for admin users.
    
    Returns:
        Response: Renders the manage users page with user data.
    """
    try:
        db = get_db()
        users = db.execute(
            text("SELECT id, username, email, role FROM users")
        ).mappings().all()
        logger.debug(f"Fetched {len(users)} users for admin management.")
        return render_template("manage_users.html", users=users)
    except Exception as e:
        logger.error(f"Error fetching user list for admin: {e}")
        return jsonify({"success": False, "error": "Failed to retrieve user data."}), 500


@bp.route("/api/users/<int:user_id>/role", methods=["PUT"])
@login_required
@admin_required
def update_user_role(user_id: int) -> tuple[Response, int]:
    """
    API endpoint to update a user's role (admin-only access).
    
    Args:
        user_id (int): The ID of the user whose role is being updated.

    Returns:
        tuple[Response, int]: JSON response with success or error message, and HTTP status code.
    """
    new_role = request.json.get("role")
    if new_role not in ["user", "admin"]:
        logger.warning(f"Invalid role '{new_role}' provided for user ID {user_id}.")
        return jsonify({"success": False, "error": "Invalid role"}), 400

    db = get_db()
    try:
        db.execute(
            text("UPDATE users SET role = :role WHERE id = :user_id"),
            {"role": new_role, "user_id": user_id}
        )
        db.commit()
        logger.info(f"User ID {user_id} role updated to '{new_role}'.")
        return jsonify({"success": True}), 200
    except Exception as e:
        log_and_rollback(db, e, "Error during user role update")
        return jsonify({"success": False, "error": "Failed to update user role"}), 500
