# app.py

import os
import logging
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, url_for
from werkzeug.wrappers import Response
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from database import close_db, init_db, init_app, db_connection
from models import User
from extensions import limiter, login_manager, csrf
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import bp as chat_bp
from routes.model_routes import bp as model_bp
from typing import Dict


# Load environment variables from .env file
load_dotenv()


# Initialize Flask app
app = Flask(__name__)


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Change to logging.INFO in production
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# Load configuration from environment variables
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
if app.config["SECRET_KEY"] == "dev-secret-key":
    logger.warning("Using default SECRET_KEY. This is insecure and should not be used in production.")
else:
    logger.debug(f"Loaded SECRET_KEY: {app.config['SECRET_KEY']}")

app.config["DATABASE"] = os.environ.get("DATABASE", "chat_app.db")


# Session cookies and security
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV') == 'production',  # Only force HTTPS in production
    SESSION_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=os.environ.get('FLASK_ENV') == 'production',  # Only force HTTPS in production
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),  # Customize as needed
)


# File upload settings
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB request size


# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# Initialize Flask-Login
login_manager.init_app(app)
login_manager.login_view = "auth.login"  # Specify the login view
login_manager.login_message_category = "info"


# Initialize CSRF Protection
csrf.init_app(app)


# Initialize Flask-Limiter
limiter.init_app(app)


# Initialize database
init_app(app)


# Register blueprints
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(chat_bp)
app.register_blueprint(model_bp, url_prefix="/models")


# Initialize database tables
with app.app_context():
    init_db()


# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    with db_connection() as db:
        user_row = db.execute(
            "SELECT id, username, email, role FROM users WHERE id = ?", (int(user_id),)
        ).fetchone()
        if user_row:
            return User(**dict(user_row))
        return None


# --- CLEANUP HANDLERS ---

# Close the database connection when the app context ends
app.teardown_appcontext(close_db)


# --- ERROR HANDLERS ---

@app.errorhandler(400)
def bad_request(error: HTTPException) -> tuple[Dict[str, str], int]:
    """Handle HTTP 400 Bad Request errors."""
    return jsonify(error="Bad request", message=error.description), 400


@app.errorhandler(403)
def forbidden(error: HTTPException) -> tuple[Dict[str, str], int]:
    """Handle HTTP 403 Forbidden errors."""
    return (
        jsonify(
            error="Forbidden",
            message="You don't have permission to access this resource.",
        ),
        403,
    )


@app.errorhandler(404)
def not_found(error: HTTPException) -> tuple[Dict[str, str], int]:
    """Handle HTTP 404 Not Found errors."""
    return (
        jsonify(error="Not found", message="The requested resource was not found."),
        404,
    )


@app.errorhandler(429)
def rate_limit_exceeded(error: HTTPException) -> tuple[Dict[str, str], int]:
    """Handle HTTP 429 Too Many Requests errors."""
    logger.warning("Rate limit exceeded: %s", error)
    return (
        jsonify(
            error="Rate limit exceeded",
            message="You have exceeded the allowed number of requests. Please try again later.",
        ),
        429,
    )


@app.errorhandler(500)
def internal_server_error(error: HTTPException) -> tuple[Dict[str, str], int]:
    """Handle HTTP 500 Internal Server Error."""
    logger.error("Internal server error: %s", error)
    return (
        jsonify(
            error="Internal server error",
            message="An unexpected error occurred. Please try again later.",
        ),
        500,
    )


@app.errorhandler(CSRFError)
def handle_csrf_error(e: CSRFError) -> tuple[Dict[str, str], int]:
    """Handle CSRF token errors raised by Flask-WTF."""
    logger.warning("CSRF error: %s", e.description)
    return (
        jsonify(
            error="CSRF Error",
            message="This request is invalid. Refresh the page and try again.",
        ),
        400,
    )


@app.errorhandler(Exception)
def handle_exception(e: Exception) -> tuple[Dict[str, str], int]:
    """Handle unhandled exceptions globally.

    Logs the error and provides a generic response to the user.
    """
    if isinstance(e, HTTPException):
        # For HTTP exceptions, pass them through with their details
        return e

    # Otherwise, log the error and return a sanitized response.
    logger.exception("Unhandled exception: %s", e)
    return (
        jsonify(
            error="Unexpected error",
            message="An unexpected error occurred. Please try again later.",
        ),
        500,
    )


# Redirect root URL to chat interface
@app.route("/")
def index() -> Response:
    """Redirect to login if not authenticated, otherwise to chat interface."""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"), code=307)
    return redirect(url_for("chat.chat_interface"), code=307)


# --- APPLICATION ENTRY POINT ---

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))  # Get port from environment or use 5000 as default
    app.run(host='0.0.0.0', port=port, debug=False)  # Ensure `debug=False` in production
