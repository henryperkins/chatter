from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from database import get_db
from models import User
import bcrypt
import logging

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required", "error")
            return render_template("login.html")

        db = get_db()
        try:
            user = db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

            if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                user_obj = User(
                    user["id"], user["username"], user["email"], user["role"]
                )
                login_user(user_obj)
                return redirect(url_for("chat.chat_interface"))
            else:
                flash("Invalid username or password", "error")
        except Exception as e:
            logger.error("Error during login: %s", str(e))
            flash("An error occurred during login", "error")

    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    if request.method == "POST":
        username = request.form.get("username", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([username, email, password, confirm_password]):
            flash("All fields are required", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("register.html")

        db = get_db()
        try:
            existing_user = db.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (username, email),
            ).fetchone()

            if existing_user:
                flash("Username or email already exists", "error")
                return render_template("register.html")

            hashed_password = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(rounds=12)
            )
            db.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, hashed_password),
            )
            db.commit()

            flash("Registration successful! Please login.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            logger.error("Error during registration: %s", str(e))
            flash("An error occurred during registration", "error")

    return render_template("register.html")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
