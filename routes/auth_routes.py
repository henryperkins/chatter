# auth_routes.py

from datetime import datetime, timedelta
import logging
import bcrypt
import uuid
from typing import Dict, List, Optional
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, jsonify,
    Response
)
from flask_login import login_user, logout_user, current_user, login_required
from database import db_connection  # Use the centralized context manager
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
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()

        with db_connection() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

            if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                user_obj = User(user["id"], user["username"], user["email"], user["role"])
                session.clear()
                login_user(user_obj)
                logger.info(f"User {user['id']} logged in successfully.")
                return redirect(url_for("chat.chat_interface"))
            else:
                logger.warning(f"Failed login attempt for username: {username}")
                flash("Invalid username or password", "error")

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
    if form.validate_on_submit():
        # Check IP-based rate limiting for failed attempts
        ip = request.remote_addr
        if not check_registration_attempts(ip):
            flash("Too many registration attempts. Please try again later.", "error")
            return render_template("register.html", form=form), 429

        username = form.username.data.strip()
        email = form.email.data.lower().strip()
        password = form.password.data

        with db_connection() as db:
            # Case-insensitive check for existing username/email
            existing_user = db.execute(
                "SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
                (username, email),
            ).fetchone()

            if existing_user:
                # Track failed attempt
                if ip not in failed_registrations:
                    failed_registrations[ip] = []
                failed_registrations[ip].append(datetime.now())

                flash("Username or email already exists", "error")
                return render_template("register.html", form=form)

            hashed_password = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(rounds=12)
            )

            # Insert new user and get the ID
            cursor = db.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, email, hashed_password, "user"),
            )
            user_id = cursor.lastrowid
            
            # Create User object and log in
            user_obj = User(user_id, username, email, "user")
            login_user(user_obj)
            flash("Registration successful!", "success")
            return redirect(url_for("chat.chat_interface"))

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
            flash("Email is required.", "error")
            return render_template("forgot_password.html")


        with db_connection() as db:
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

            if not user:
                flash("No account found with that email address.", "error")
                return render_template("forgot_password.html")

            # Generate a password reset token (for simplicity, using a UUID here)
            reset_token = str(uuid.uuid4())
            db.execute(
                "UPDATE users SET reset_token = ?, reset_token_expiry = datetime('now', '+1 hour') WHERE email = ?",
                (reset_token, email),
            )
            flash("A password reset link has been sent to your email.", "success")
            return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")

    # Reset Password route
    @bp.route("/reset_password/<token>", methods=["GET", "POST"])
    @limiter.limit("5 per minute")
    def reset_password(token):
        """
        Handle the password reset using the provided token.
        """
        form = ResetPasswordForm()
        with db_connection() as db:
            user = db.execute(
                "SELECT * FROM users WHERE reset_token = ? AND reset_token_expiry > datetime('now')",
                (token,),
            ).fetchone()

            if not user:
                flash("Invalid or expired reset token.", "error")
                return redirect(url_for("auth.login"))

            if form.validate_on_submit():
                password = form.password.data.strip()
                hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))

                db.execute(
                    "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?",
                    (hashed_password, user["id"]),
                )
                flash("Your password has been reset successfully.", "success")
                return redirect(url_for("auth.login"))

        return render_template("reset_password.html", form=form, token=token)



# Manage Users route (admin-only access)
@bp.route("/manage-users")
@login_required
@admin_required
def manage_users() -> Response:
    with db_connection() as db:
        users = db.execute("SELECT id, username, email, role FROM users").fetchall()
        return render_template("manage_users.html", users=users)



# API endpoint to update a user's role (admin-only access)
@bp.route("/api/users/<int:user_id>/role", methods=["PUT"])
@login_required
@admin_required
def update_user_role(user_id: int) -> tuple[Response, int]:
    new_role = request.json.get("role")
    if new_role not in ["user", "admin"]:
        return jsonify({"error": "Invalid role"}), 400

    with db_connection() as db:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        return jsonify({"success": True})
