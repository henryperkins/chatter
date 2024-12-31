from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from database import get_db
from models import User
import bcrypt

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required")
            return render_template("login.html")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
            user_obj = User(user["id"], user["username"], user["email"])
            login_user(user_obj)
            return redirect(url_for("chat.chat_interface"))

        flash("Invalid username or password")
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    if request.method == "POST":
        username = request.form.get("username", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        if not all([username, email, password]):
            flash("All fields are required")
            return render_template("register.html")

        db = get_db()
        # Combine username and email check into one
        existing_user = db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?", (username, email)
        ).fetchone()

        if existing_user:
            flash("Username or email already exists")
            return render_template("register.html")

        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, hashed_password),
        )
        db.commit()

        flash("Registration successful! Please login.")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
