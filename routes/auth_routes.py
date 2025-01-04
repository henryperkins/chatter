from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
)
from flask_login import login_user, logout_user, current_user, login_required
from database import get_db
from models import User
from decorators import admin_required
import bcrypt
import logging
from forms import LoginForm, RegistrationForm

# Define the blueprint
bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# Login route with rate-limiting
@bp.route("/login", methods=["GET", "POST"])
def login():
    # Import limiter dynamically to avoid circular imports
    from app import limiter
    login = limiter.limit("5/minute")(login)

    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))  # Redirect if user is already logged in

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()

        db = get_db()  # Get a database connection
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


# Registration route
@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))  # Redirect if user is already logged in

    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip()
        password = form.password.data.strip()

        db = get_db()
        existing_user = db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()

        if existing_user:
            flash("Username or email already exists", "error")
            return render_template("register.html", form=form)

        hashed_password = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=12)
        )

        db.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, hashed_password, "user"),
        )
        db.commit()

        flash("Registration successful! Please check your email to confirm your account.", "success")
        return redirect(url_for("auth.login"))
    
    return render_template("register.html", form=form)


# Logout route
@bp.route("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


# Manage users route (admin-only access)
@bp.route("/manage-users")
@login_required
@admin_required
def manage_users():
    db = get_db()
    users = db.execute("SELECT id, username, email, role FROM users").fetchall()
    return render_template("manage_users.html", users=users)


# API endpoint to update a user's role (admin-only access)
@bp.route("/api/users/<int:user_id>/role", methods=["PUT"])
@login_required
@admin_required
def update_user_role(user_id):
    new_role = request.json.get("role")
    if new_role not in ["user", "admin"]:
        return jsonify({"error": "Invalid role"}), 400

    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    db.commit()
    return jsonify({"success": True})