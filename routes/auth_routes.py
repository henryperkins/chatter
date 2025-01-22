"""
Authentication routes for the application.
"""

import logging
import os
import secrets, hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from email_validator import validate_email
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError, validate_csrf
from wtforms.validators import ValidationError
from sqlalchemy import text

from chat_utils import handle_error, send_reset_email
from config import Config
from database import db_session  # Import db_session from centralized database module
from decorators import admin_required
from extensions import limiter
from forms import LoginForm, RegistrationForm, ResetPasswordForm
from models import Model, User, user
from .auth_utils import (  # Remove db_session from auth_utils imports
    check_attempts,
    limiter_key,
    log_failed_attempt,
    failed_logins,
    failed_registrations,
)

# Define the blueprint
bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


@bp.route("/manage_users", methods=["GET"])
@login_required
@admin_required
def manage_users():
    """Render the manage users page."""
    logger.info(
        "Accessed manage users page",
        extra={
            "ip_address": request.remote_addr,
            "route": request.path,
            "user_id": current_user.id,
        },
    )
    return render_template("manage_users.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", key_func=limiter_key)
def login():
    """Handle user login requests."""
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    form = LoginForm()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Username and password are required", "error")
            return render_template("login.html", form=form)

        try:
            with db_session() as db:
                # Get user with proper transaction handling
                query = text("""
                    SELECT id, username, email, password_hash, role 
                    FROM users 
                    WHERE username = :username
                    AND is_active = TRUE
                    FOR UPDATE
                """)
                result = db.execute(query, {"username": username}).mappings().first()

                if not result:
                    flash("Invalid username or password", "error")
                    return render_template("login.html", form=form)

                password_hash = result["password_hash"]
                if isinstance(password_hash, bytes):
                    password_hash = password_hash.decode('utf-8')

                if not check_password_hash(password_hash, password):
                    flash("Invalid username or password", "error")
                    return render_template("login.html", form=form)

                # Create user object and login with session management
                user = User(
                    id=result["id"],
                    username=result["username"],
                    email=result["email"],
                    role=result["role"]
                )
                login_user(user)
                
                # Set session data
                session.permanent = True
                session['user_id'] = user.id
                session['last_active'] = datetime.now().isoformat()
                
                return redirect(url_for("chat.chat_interface"))

        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            flash("An error occurred during login. Please try again.", "error")
            return render_template("login.html", form=form)

    return render_template("login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration requests."""
    if current_user.is_authenticated:
        return redirect(url_for("chat.chat_interface"))

    form = RegistrationForm()
    if request.method == "POST":
        try:
            if form.validate_on_submit():
                username = form.username.data.strip()
                email = form.email.data.lower().strip()
                password = form.password.data

                with db_session() as db:
                    # Check for existing user without FOR UPDATE
                    query = text("""
                        SELECT COUNT(*) as count 
                        FROM users 
                        WHERE username = :username OR email = :email
                    """)
                    result = db.execute(query, {
                        "username": username,
                        "email": email
                    }).scalar()

                    if result > 0:
                        flash("Username or email already exists", "error")
                        return render_template("register.html", form=form)

                    # Create new user with proper error handling
                    try:
                        password_hash = generate_password_hash(password)
                        if isinstance(password_hash, bytes):
                            password_hash = password_hash.decode('utf-8')

                        # Use a transaction for the insert
                        insert_query = text("""
                            INSERT INTO users (username, email, password_hash, role)
                            VALUES (:username, :email, :password_hash, 'user')
                            RETURNING id, username, email, role
                        """)
                        result = db.execute(insert_query, {
                            "username": username,
                            "email": email,
                            "password_hash": password_hash
                        }).mappings().first()

                        if not result:
                            raise ValueError("Failed to create user")

                        # Create user object and login
                        user = User(
                            id=result["id"],
                            username=result["username"],
                            email=result["email"],
                            role=result["role"]
                        )
                        login_user(user)
                        
                        # Commit the transaction
                        db.commit()
                        
                        return redirect(url_for("chat.chat_interface"))
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Error creating user: {str(e)}")
                        flash("Error creating user account", "error")
                        return render_template("register.html", form=form)

        except Exception as e:
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            flash("An error occurred during registration. Please try again.", "error")
            return render_template("register.html", form=form)

    return render_template("register.html", form=form)


@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    """Handle forgot password requests."""
    form = ResetPasswordForm()  # Initialize form
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        try:
            if not validate_email(email):
                logger.warning(
                    "Invalid email address provided for password reset",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "email": email,
                    },
                )
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Please provide a valid email address.",
                        }
                    ),
                    400,
                )

            with db_session() as db:
                user = (
                    db.execute(
                        text("SELECT id, email FROM users WHERE email = :email"),
                        {"email": email},
                    )
                    .mappings()
                    .first()
                )

                if not user:
                    logger.info(
                        "Password reset requested for non-existent email",
                        extra={
                            "ip_address": request.remote_addr,
                            "route": request.path,
                            "email": email,
                        },
                    )
                    return (
                        jsonify(
                            {
                                "success": True,
                                "message": (
                                    "If an account exists with this email, "
                                    "you will receive password reset instructions."
                                ),
                            }
                        ),
                        200,
                    )

                reset_token = secrets.token_urlsafe(32)
                reset_token_hash = generate_password_hash(reset_token)

                db.execute(
                    text(
                        """
                        UPDATE users
                        SET reset_token_hash = :token_hash,
                            reset_token_expiry = NOW() + INTERVAL '1 hour'
                        WHERE email = :email
                    """
                    ),
                    {"token_hash": reset_token_hash, "email": email},
                )

                reset_url = url_for(
                    "auth.reset_password", token=reset_token, _external=True
                )
                send_reset_email(email, reset_url)

                logger.info(
                    "Password reset email sent",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "email": email,
                    },
                )
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": (
                                "If an account exists with this email, "
                                "you will receive password reset instructions."
                            ),
                        }
                    ),
                    200,
                )

        except Exception as e:
            logger.error(
                f"Error during password reset: {e}",
                exc_info=True,
                extra={
                    "ip_address": request.remote_addr,
                    "route": request.path,
                    "email": email,
                },
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "An error occurred. Please try again later.",
                    }
                ),
                500,
            )

    return render_template("forgot_password.html", form=form)  # Pass form to template

@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token: str):
    """Handle password reset requests."""
    form = ResetPasswordForm()

    try:
        with db_session() as db:
            user = (
                db.execute(
                    text(
                        "SELECT * FROM users WHERE reset_token_expiry > NOW() AND reset_token_hash IS NOT NULL"
                    )
                )
                .mappings()
                .first()
            )

            if not user or not check_password_hash(
                user["reset_token_hash"], token
            ):
                logger.warning(
                    "Invalid or expired reset token used",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "token": token,
                    },
                )
                return (
                    jsonify(
                        {"success": False, "error": "Invalid or expired reset token."}
                    ),
                    400,
                )

            if request.method == "POST" and form.validate_on_submit():
                hashed_password = generate_password_hash(form.password.data.strip() if form.password.data else "")
                if isinstance(hashed_password, bytes):
                    hashed_password = hashed_password.decode("utf-8")

                db.execute(
                    text(
                        """
                        UPDATE users
                        SET password_hash = :password_hash,
                            reset_token_hash = NULL,
                            reset_token_expiry = NULL
                        WHERE id = :user_id
                    """
                    ),
                    {"password_hash": hashed_password, "user_id": user["id"]},
                )

                logger.info(
                    "Password reset successfully",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "user_id": user["id"],
                    },
                )
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": "Your password has been reset successfully.",
                        }
                    ),
                    200,
                )

            elif request.method == "POST":
                logger.warning(
                    "Password reset form validation failed",
                    extra={
                        "ip_address": request.remote_addr,
                        "route": request.path,
                        "errors": form.errors,
                    },
                )
                return jsonify({"success": False, "errors": form.errors}), 400

            return render_template("reset_password.html", form=form)

    except Exception as e:
        logger.error(
            f"Error during password reset: {e}",
            exc_info=True,
            extra={
                "ip_address": request.remote_addr,
                "route": request.path,
                "token": token,
            },
        )
        return jsonify({"success": False, "error": "An unexpected error occurred"}), 500




@bp.route("/logout")
@login_required
def logout():
    """Handle user logout."""
    logger.info(
        "User logged out",
        extra={
            "user_id": current_user.id,
            "ip_address": request.remote_addr,
            "route": request.path,
            "session_duration": (datetime.now() - session.get('login_time', datetime.now())).total_seconds()
        }
    )
    logout_user()
    return redirect(url_for("auth.login"))
