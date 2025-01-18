import uuid
import os
from datetime import timedelta
from typing import Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, url_for, request, session, g
from flask_login import current_user, logout_user
from flask_talisman import Talisman
from flask_sslify import SSLify
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.wrappers import Response as WerkzeugResponse
from sqlalchemy import text

from database import init_app, get_db
from extensions import limiter, login_manager, csrf
from models import User
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import chat_routes
from routes.model_routes import bp as model_bp
from config import Config  # Import centralized configuration

from logging_config import get_logger

logger = get_logger(__name__)

# Load environment variables
load_dotenv(dotenv_path=".env")

# Initialize Flask app
app = Flask(__name__)


# Middleware to handle Connection: Upgrade header
class RemoveConnectionUpgradeMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Check if 'Connection' header exists and contains 'Upgrade'
        connection_header = environ.get("HTTP_CONNECTION", "")
        if "upgrade" in connection_header.lower():
            # Remove 'Upgrade' from the 'Connection' header
            environ["HTTP_CONNECTION"] = "close"
            logger.debug(
                f"Modified Connection header from '{connection_header}' to 'close'"
            )
        return self.app(environ, start_response)


# Wrap the Flask app with the middleware
app.wsgi_app = RemoveConnectionUpgradeMiddleware(app.wsgi_app)

# Configure Flask-Limiter to use Redis
limiter.init_app(app)


# --- Configuration Functions ---
def configure_security() -> None:
    """Configure security settings"""
    if app.config.get("ENV") == "production":
        # Enable HTTPS only in production
        SSLify(app)
        Talisman(app)
        app.config.update(
            SESSION_COOKIE_SECURE=True,
            REMEMBER_COOKIE_SECURE=True,
            PREFERRED_URL_SCHEME="https",
        )

    # Basic security settings for all environments
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )


def configure_app() -> None:
    """Configure Flask application settings"""
    # Basic configuration
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["DATABASE_URI"] = Config.DATABASE_URI

    # File upload settings
    app.config.update(
        UPLOAD_FOLDER=Config.UPLOAD_FOLDER,
        MAX_CONTENT_LENGTH=Config.MAX_TOTAL_FILE_SIZE,
        MAX_FILE_SIZE=Config.MAX_FILE_SIZE,
        MAX_FILES=5,
        ALLOWED_FILE_TYPES=list(Config.ALLOWED_FILE_EXTENSIONS),
    )

    # Password policy settings
    app.config.update(
        PASSWORD_MIN_LENGTH=Config.PASSWORD_MIN_LENGTH,
        PASSWORD_REQUIRE_UPPERCASE=Config.PASSWORD_REQUIRE_UPPERCASE,
        PASSWORD_REQUIRE_LOWERCASE=Config.PASSWORD_REQUIRE_LOWERCASE,
        PASSWORD_REQUIRE_NUMBER=Config.PASSWORD_REQUIRE_NUMBER,
        PASSWORD_REQUIRE_SPECIAL_CHAR=Config.PASSWORD_REQUIRE_SPECIAL_CHAR,
    )

    # Session settings
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),
        WTF_CSRF_HEADERS=["X-CSRFToken"],
        WTF_CSRF_ENABLED=True,
    )

    # Rate limiting is now configured in extensions.py with Redis


def init_app_components() -> None:
    """Initialize Flask extensions and components"""
    # Apply proxy fix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Initialize extensions
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # type: ignore

    csrf.init_app(app)
    limiter.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(chat_routes, url_prefix="/chat")
    app.register_blueprint(model_bp, url_prefix="/models")

    # Check if auth routes are properly registered
    if "auth.register" not in app.view_functions:
        logger.error("Auth routes failed to register properly")
        raise RuntimeError("Auth routes failed to register properly")

    # Initialize database
    init_app(app)

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# --- Error Handlers ---
@app.errorhandler(400)
def bad_request(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 400 Bad Request errors"""
    logger.exception("400 Bad Request - URL: %s", request.url)
    return (
        jsonify(error="Bad request", message=error.description or "Invalid request"),
        400,
    )


@app.errorhandler(401)
def unauthorized(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 401 Unauthorized errors"""
    logger.warning(f"Unauthorized access attempt: {str(error)}")
    return jsonify(error="Unauthorized", message="Please login to access this resource"), 401


@app.errorhandler(403)
def forbidden(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 403 Forbidden errors"""
    logger.warning(f"Forbidden access attempt: {str(error)}")
    return jsonify(error="Forbidden", message="Access denied"), 403


@app.errorhandler(404)
def not_found(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 404 Not Found errors"""
    logger.info(f"Resource not found: {str(error)}")
    return jsonify(error="Not found", message="Resource not found"), 404


@app.errorhandler(429)
def rate_limit_exceeded(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 429 Too Many Requests errors"""
    return jsonify(error="Rate limit exceeded", message="Please try again later"), 429


@app.errorhandler(500)
def internal_server_error(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 500 Internal Server Error"""
    logger.error(f"500 Internal Server Error: {error} - URL: {request.url}")
    return (
        jsonify(error="Internal server error", message="An unexpected error occurred"),
        500,
    )


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all uncaught exceptions"""
    if request.path.startswith("/static/"):
        # Let Flask handle static file exceptions
        raise e

    logger.exception(
        "Unhandled exception occurred - URL: %s, Method: %s, User: %s, Error: %s",
        request.url,
        request.method,
        current_user.id if current_user.is_authenticated else "anonymous",
        str(e),
    )

    if app.config.get("ENV") == "production":
        return jsonify(error="Internal server error", message="Please try again later"), 500
    else:
        return jsonify(error="Internal server error", message=str(e)), 500


@app.errorhandler(CSRFError)
def handle_csrf_error(e: CSRFError) -> Tuple[WerkzeugResponse, int]:
    """Handle CSRF token errors"""
    return (
        jsonify(error="Invalid CSRF token", message="Please refresh and try again"),
        400,
    )


# --- Request Hooks ---
@app.before_request
def log_request_info():
    """Log request information with correlation ID and user context."""
    try:
        g.correlation_id = str(uuid.uuid4())
        if current_user.is_authenticated:
            g.user_id = current_user.id
        # Log request information only once
        if not hasattr(g, "_request_logged"):
            logger.debug(
                "Request received - Method: %s, Path: %s, Remote: %s, Correlation ID: %s, User ID: %s",
                request.method,
                request.path,
                request.remote_addr,
                g.correlation_id,
                getattr(g, "user_id", None),
            )
            g._request_logged = True
    except Exception as e:
        logger.error(
            "Error logging request",
            extra={
                "error": str(e),
                "correlation_id": getattr(g, "correlation_id", None),
            },
        )


# --- Routes ---
@app.route("/favicon.ico")
def favicon() -> WerkzeugResponse:
    """Handle favicon requests"""
    return redirect(url_for("static", filename="favicon.ico"))


@app.route("/")
def index() -> WerkzeugResponse:
    """Root URL handler"""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("chat.chat_interface"))


@app.route("/clear-session")
def clear_session() -> WerkzeugResponse:
    """Clear user session"""
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


# --- User Loader ---
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user by ID"""
    db = None
    try:
        db = get_db()
        result = db.execute(
            text("SELECT id, username, email, role FROM users WHERE id = :id"),
            {"id": int(user_id)},
        ).fetchone()
        return (
            User(**dict(zip(["id", "username", "email", "role"], result)))
            if result
            else None
        )
    except Exception as e:
        app.logger.error(f"Error loading user: {e}")
        return None
    finally:
        if db is not None:
            db.close()


# --- Application Initialization ---
configure_app()
configure_security()
init_app_components()

# --- Application Entry Point ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
