import os
import logging
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, url_for, request, session
from werkzeug.wrappers import Response
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from database import close_db, init_db, init_app, get_db
from sqlalchemy import text
from models import User, Model
import redis  # Add this import
from extensions import limiter, login_manager, csrf
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import chat_routes
from routes.model_routes import bp as model_bp
from typing import Dict, Optional
from database import close_db, init_db, init_app, get_db

# Load environment variables from .env file
load_dotenv()

from werkzeug.middleware.proxy_fix import ProxyFix

from flask_sslify import SSLify

# Initialize Flask app
app = Flask(__name__)

# Enforce HTTPS in production
if not app.testing:
    sslify = SSLify(app)
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        PREFERRED_URL_SCHEME="https"
    )

# Apply ProxyFix middleware
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Change to logging.INFO in production
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Load configuration from environment variables
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

# Add default configurations if not set
app.config.setdefault('MAX_FILE_SIZE', 10 * 1024 * 1024)  # 10 MB
app.config.setdefault('MAX_FILES', 5)
app.config.setdefault('MAX_MESSAGE_LENGTH', 1000)
app.config.setdefault('ALLOWED_FILE_TYPES', ["text/plain", "application/pdf", "image/jpeg", "image/png"])
if (
    app.config["SECRET_KEY"] == "dev-secret-key"
    and os.environ.get("FLASK_ENV") == "production"
):
    logger.error(
        "Using default SECRET_KEY in production is insecure. Please set a secure SECRET_KEY in your environment variables."
    )
else:
    logger.debug(f"Loaded SECRET_KEY: {app.config['SECRET_KEY']}")

app.config["DATABASE"] = os.environ.get("DATABASE", "chat_app.db")

# Session cookies and security
is_behind_proxy = os.environ.get("BEHIND_PROXY", "False") == "True"

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=is_behind_proxy,  # Use HTTPS settings if behind a proxy
    SESSION_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=is_behind_proxy,
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

# Add this line to tell Flask-WTF where to look for the CSRF token
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']

# Configure CSRF Protection
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # Disable default CSRF checks
app.config['WTF_CSRF_METHODS'] = []  # Disable CSRF for all methods by default
csrf.init_app(app)

# Configure Flask-Limiter
app.config.update({
    "RATELIMIT_STRATEGY": "fixed-window",  # Use simpler strategy
    "RATELIMIT_DEFAULT": "200 per day;50 per hour",  # Set reasonable defaults
})

# Check Redis availability and configure storage
def is_redis_available():
    try:
        redis_client = redis.StrictRedis.from_url("redis://localhost:6379")
        redis_client.ping()  # Test connection
        return True
    except redis.ConnectionError:
        return False

# Initialize limiter with SQLite storage
limiter.init_app(app, storage_uri="sqlite:///rate_limits.db")
logger.info("Using SQLite for rate limiting storage.")

# Initialize database
init_app(app)

# Inject app configuration into templates
@app.context_processor
def inject_config():
    return dict(config=app.config)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(chat_routes, url_prefix="/chat")
app.register_blueprint(model_bp, url_prefix="/models")

# Initialize database and default model
def init_app_data():
    """Initialize database and create default model if needed."""
    try:
        init_db()
        logger.info("Database initialized successfully")

        # Get database connection from pool
        db = get_db()
        try:
            # Check for existing models
            model_count = db.execute(text("SELECT COUNT(*) FROM models")).scalar()
            if model_count == 0:
                logger.info("No models found - creating default model")
                try:
                    Model.create_default_model()
                    logger.info("Default model created successfully")
                except ValueError as e:
                    logger.error(f"Default model configuration is invalid: {e}")
                    logger.error("Please fix the default model configuration and restart the application.")
                    raise
            else:
                logger.debug(f"Found {model_count} existing models")
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error during app data initialization: {e}")
        raise

# Initialize core application components
with app.app_context():
    try:
        init_app_data()
    except Exception as e:
        logger.critical(f"Failed to initialize application: {e}")
        raise

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """
    load_user _summary_

    _extended_summary_

    Args:
        user_id (str): _description_

    Returns:
        Optional[User]: _description_
    """
    db = get_db()
    try:
        result = db.execute(
            text("SELECT id, username, email, role FROM users WHERE id = :id"),
            {"id": int(user_id)},
        ).fetchone()
        if result:
            # Convert tuple to dictionary with known column order
            user_dict = {
                "id": result[0],
                "username": result[1],
                "email": result[2],
                "role": result[3],
            }
            logger.debug(f"Loading user: {user_dict}")
            return User(**user_dict)
        return None
    except Exception as e:
        logger.error(f"Error loading user: {e}")
        return None
    finally:
        db.close()


# Close the database connection when the app context ends
app.teardown_appcontext(close_db)

# --- ERROR HANDLERS ---

@app.errorhandler(400)
def bad_request(error: HTTPException) -> tuple[Dict[str, str], int]:
    """Handle HTTP 400 Bad Request errors."""
    return (
        jsonify(
            error="Bad request",
            message=error.description
            or "The request was invalid. Please check your input and try again.",
        ),
        400,
    )


@app.errorhandler(403)
def forbidden(error: HTTPException) -> tuple[Dict[str, str], int]:
    """Handle HTTP 403 Forbidden errors."""
    logger.warning(
        f"Forbidden access attempt by user {current_user.username if current_user.is_authenticated else 'anonymous'} to {request.path}"
    )
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
    """Handle unhandled exceptions globally."""
    if isinstance(e, HTTPException):
        return e
    logger.exception("Unhandled exception: %s", e)
    if "database" in str(e).lower():
        return (
            jsonify(
                error="Database error",
                message="An error occurred while accessing the database. Please try again later.",
            ),
            500,
        )
    elif "file upload" in str(e).lower():
        return (
            jsonify(
                error="File upload error",
                message="An error occurred while uploading your file. Please check the file and try again.",
            ),
            500,
        )
    return (
        jsonify(
            error="Unexpected error",
            message="An unexpected error occurred. Please try again later.",
        ),
        500,
    )


# Handle favicon.ico requests
@app.route("/favicon.ico")
def favicon() -> Response:
    """Redirect favicon.ico requests to the static file."""
    return redirect(url_for("static", filename="favicon.ico"))


# Redirect root URL to chat interface
@app.route("/")
def index() -> Response:
    """Redirect to login if not authenticated, otherwise to chat interface."""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"), code=307)
    return redirect(url_for("chat.chat_interface"), code=307)


# Clear session route
@app.route("/clear-session")
def clear_session() -> Response:
    """Clear the session and log out the user."""
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


# --- APPLICATION ENTRY POINT ---

if __name__ == "__main__":
    port = int(
        os.environ.get("PORT", 5000)
    )  # Get port from environment or use 5000 as default
    app.run(host="0.0.0.0", port=port, debug=True)  # Set debug=True for development
from flask_talisman import Talisman

# Apply security headers
Talisman(app, content_security_policy={
    'default-src': "'self'",
    'script-src': "'self' 'unsafe-inline'",
    'style-src': "'self' 'unsafe-inline'",
    'img-src': "'self' data:",
    'connect-src': "'self'",
    'font-src': "'self'",
    'object-src': "'none'",
    'frame-src': "'none'"
})
