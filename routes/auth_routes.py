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

# Login route with rate-limiting
@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5/minute")  # Apply the limiter decorator here
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))  # Redirect if user is already logged in

    form = LoginForm()
    if request.method == "POST":
        if form.validate_on_submit():
            username = form.username.data.strip()
            password = form.password.data.strip()

            db = get_db()
            user = db.execute(
                text("SELECT * FROM users WHERE username = :username"),
                {"username": username}
            ).fetchone()

            if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                user_obj = User(user["id"], user["username"], user["email"], user["role"])
                session.clear()
                login_user(user_obj)
                logger.info(f"User {user['id']} logged in successfully.")
                return jsonify({"success": True, "message": "Login successful"}), 200
            else:
                logger.warning(f"Failed login attempt for username: {username}")
                return jsonify({"success": False, "error": "Invalid username or password"}), 401
        else:
            return jsonify({"success": False, "errors": form.errors}), 400

    return render_template("login.html", form=form)

def check_registration_attempts(ip: str) -> bool:
    """Check if IP has exceeded failed registration attempts"""
    now = datetime.now()
    if ip in failed_registrations:
        # Clean up old attempts
        failed_registrations[ip] = [
            timestamp for timestamp in failed_registrations[ip]
            if now - timestamp < timedelta(minutes=15)
        ]
        # Check if too many recent attempts
        if len(failed_registrations[ip]) >= 5:
            return False
    return True

# Registration route
@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register() -> Response:
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))  # Redirect if user is already logged in

    form = RegistrationForm()
    if request.method == "POST":
        # Check IP-based rate limiting for failed attempts
        ip = request.remote_addr
        if not check_registration_attempts(ip):
            return jsonify({"success": False, "error": "Too many registration attempts. Please try again later."}), 429

        if form.validate_on_submit():
            username = form.username.data.strip()
            email = form.email.data.lower().strip()
            password = form.password.data

            db = get_db()
            # Case-insensitive check for existing username/email
            existing_user = db.execute(
                text("SELECT id FROM users WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)"),
                {"username": username, "email": email}
            ).fetchone()

            if existing_user:
                # Track failed attempt
                if ip not in failed_registrations:
                    failed_registrations[ip] = []
                failed_registrations[ip].append(datetime.now())

                return jsonify({"success": False, "error": "Username or email already exists"}), 400

            hashed_password = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(rounds=12)
            )

            try:
                db.execute(
                    text("INSERT INTO users (username, email, password_hash, role) VALUES (:username, :email, :password_hash, :role)"),
                    {
                        "username": username,
                        "email": email,
                        "password_hash": hashed_password,
                        "role": "user"
                    }
                )
                db.commit()
                return jsonify({"success": True, "message": "Registration successful! Please check your email to confirm your account."}), 200
            except Exception as e:
                db.rollback()
                logger.error(f"Database error during registration: {e}")
                return jsonify({"success": False, "error": "Registration failed due to database error"}), 500
        else:
            return jsonify({"success": False, "errors": form.errors}), 400

    return render_template("register.html", form=form)

# Logout route
@bp.route("/logout")
@login_required
def logout() -> Response:
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))

# Forgot Password route
@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password() -> Response:
    """
    Handle the forgot password functionality.
    """
    if request.method == "POST":
        email = request.form.get("email").strip()

        # Validate email
        if not email:
            return jsonify({"success": False, "error": "Email is required."}), 400

        db = get_db()
        user = db.execute(
            text("SELECT * FROM users WHERE email = :email"),
            {"email": email}
        ).fetchone()

        if not user:
            return jsonify({"success": False, "error": "No account found with that email address."}), 404

        # Generate a password reset token (for simplicity, using a UUID here)
        try:
            reset_token = str(uuid.uuid4())
            db.execute(
                text("UPDATE users SET reset_token = :token, reset_token_expiry = datetime('now', '+1 hour') WHERE email = :email"),
                {
                    "token": reset_token,
                    "email": email
                }
            )
            db.commit()
            # In a real application, you would send an email here with the reset link
            return jsonify({"success": True, "message": "A password reset link has been sent to your email."}), 200
        except Exception as e:
            db.rollback()
            logger.error(f"Database error during password reset: {e}")
            return jsonify({"success": False, "error": "Failed to process password reset"}), 500

    return render_template("forgot_password.html")

# Reset Password route
@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token):
    """
    Handle the password reset using the provided token.
    """
    form = ResetPasswordForm()
    db = get_db()
    user = db.execute(
        text("SELECT * FROM users WHERE reset_token = :token AND reset_token_expiry > datetime('now')"),
        {"token": token}
    ).fetchone()

    if not user:
        return jsonify({"success": False, "error": "Invalid or expired reset token."}), 400

    if request.method == "POST" and form.validate_on_submit():
        password = form.password.data.strip()
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))

        db.execute(
            text("UPDATE users SET password_hash = :password_hash, reset_token = NULL, reset_token_expiry = NULL WHERE id = :user_id"),
            {
                "password_hash": hashed_password,
                "user_id": user["id"]
            }
        )
        db.commit() # Added to commit the changes to the database.
        return jsonify({"success": True, "message": "Your password has been reset successfully."}), 200
    elif request.method == "POST":
        return jsonify({"success": False, "errors": form.errors}), 400

    return render_template("reset_password.html", form=form, token=token)

# Manage Users route (admin-only access)
@bp.route("/manage-users")
@login_required
@admin_required
def manage_users() -> Response:
    db = get_db()
    users = db.execute(text("SELECT id, username, email, role FROM users")).fetchall()
    return render_template("manage_users.html", users=users)

# API endpoint to update a user's role (admin-only access)
@bp.route("/api/users/<int:user_id>/role", methods=["PUT"])
@login_required
@admin_required
def update_user_role(user_id: int) -> tuple[Response, int]:
    new_role = request.json.get("role")
    if new_role not in ["user", "admin"]:
        return jsonify({"success": False, "error": "Invalid role"}), 400

    db = get_db()
    try:
        db.execute(
            text("UPDATE users SET role = :role WHERE id = :user_id"),
            {"role": new_role, "user_id": user_id}
        )
        db.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Database error during role update: {e}")
        return jsonify({"success": False, "error": "Failed to update user role"}), 500