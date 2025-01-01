"""Flask application initialization and configuration module.

This module sets up the Flask application, configures logging, initializes
Flask-Login, and registers blueprints for authentication, chat, and model routes.
It also includes error handlers for common HTTP error codes.
"""

import logging
import os
from flask import Flask, jsonify
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException

from database import get_db, close_db, init_db, init_app
from models import User
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import bp as chat_bp
from routes.model_routes import bp as model_bp
from datetime import timedelta

# Initialize Flask app
app = Flask(__name__)

# Simplified Configuration (Directly in app.py)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "your-secret-key")
app.config["LOGGING_LEVEL"] = logging.DEBUG  # Set to logging.INFO for production
app.config["LOGGING_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Session Security Settings
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,  # Ensure the app is served over HTTPS
    SESSION_COOKIE_SAMESITE='Lax',
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=True,  # Ensure the app is served over HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),  # Adjust as needed
)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Initialize database connection
init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(model_bp)

# Initialize database tables
with app.app_context():
    init_db()

# Configure logging
logging.basicConfig(
    level=app.config["LOGGING_LEVEL"],
    format=app.config["LOGGING_FORMAT"],
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load user by ID for Flask-Login.

    Args:
        user_id: The user ID to load from the database

    Returns:
        User object if found, None otherwise
    """
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if user:
        return User(user["id"], user["username"], user["email"], user["role"])
    return None

# Teardown database connection
app.teardown_appcontext(close_db)

# Error handlers
@app.errorhandler(400)
def bad_request(error):
    """Handle 400 Bad Request errors."""
    return jsonify(error="Bad request", message=error.description), 400

@app.errorhandler(403)
def forbidden(error):
    """Handle 403 Forbidden errors."""
    return (
        jsonify(
            error="Forbidden",
            message="You don't have permission to access this resource.",
        ),
        403,
    )

@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors."""
    return (
        jsonify(error="Not found", message="The requested resource was not found."),
        404,
    )

@app.errorhandler(500)
def internal_server_error(error):
    """Handle 500 Internal Server Error errors."""
    logger.error("Server error: %s", error)
    return (
        jsonify(error="Internal server error", message="An unexpected error occurred."),
        500,
    )

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle any unhandled exceptions."""
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e
    # Log the error and stacktrace.
    logger.exception(e)
    return (
        jsonify(error="Internal server error", message="An unexpected error occurred."),
        500,
    )

if __name__ == "__main__":
    app.run(debug=True)  # Set debug=False in production