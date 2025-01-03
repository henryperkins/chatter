from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
from flask_login import login_user, logout_user, current_user, login_required
from database import get_db
from models import User
from decorators import admin_required  # Add this import
import bcrypt
import logging
import os
from forms import LoginForm, RegistrationForm

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
            user_obj = User(user["id"], user["username"], user["email"], user["role"])
            session.clear()
            login_user(user_obj)
            return redirect(url_for("chat.chat_interface"))
        else:
            flash("Invalid username or password", "error")
    return render_template("login.html", form=form)

@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))
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
        # All new users have 'user' role; admins set manually
        db.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, hashed_password, "user"),
        )
        db.commit()

        flash("Registration successful! Please check your email to confirm your account.", "success")
        return redirect(url_for("auth.login"))
    return render_template("register.html", form=form)

@bp.route("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))

@bp.route("/manage-users")
@login_required
@admin_required
def manage_users():
    """Admin interface for managing user roles."""
    db = get_db()

    users = db.execute("SELECT id, username, email, role FROM users").fetchall()
    return render_template("manage_users.html", users=users)

@bp.route("/api/users/<int:user_id>/role", methods=["PUT"])
@login_required
@admin_required
def update_user_role(user_id):
    """Update a user's role."""
    new_role = request.json.get("role")
    if new_role not in ["user", "admin"]:
        return jsonify({"error": "Invalid role"}), 400

    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    db.commit()
    return jsonify({"success": True})
