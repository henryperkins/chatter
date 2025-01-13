import logging
import os
from datetime import timedelta
from typing import Optional, Union

from dotenv import load_dotenv
from flask import Flask, Response as FlaskResponse, jsonify, redirect, request, session, url_for
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from database import close_db, get_db, init_app, init_db
from extensions import csrf, limiter, login_manager
from models import User
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import chat_routes
from routes.model_routes import bp as model_bp

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

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

# Configure Flask-Limiter with in-memory storage
app.config.update(
    {
        "RATELIMIT_STORAGE_URL": "memory://",
        "RATELIMIT_STRATEGY": "fixed-window",
        "RATELIMIT_DEFAULT": "1000 per day;200 per hour",  # More lenient default
    }
)

# More permissive rate limits for static files
limiter.limit("1000 per hour")(app.route("/static/<path:filename>"))
limiter.limit("1000 per hour")(app.route("/favicon.ico"))
limiter.init_app(app)

# Initialize database
init_app(app)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(chat_routes, url_prefix="/chat")
app.register_blueprint(model_bp, url_prefix="/models")

# Initialize database tables
with app.app_context():
    init_db()


# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
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


# --- CLEANUP HANDLERS ---

# Close the database connection when the app context ends
app.teardown_appcontext(close_db)

# --- ERROR HANDLERS ---


@app.errorhandler(400)
def bad_request(error: HTTPException) -> tuple[Union[FlaskResponse, dict], int]:
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
def forbidden(error: HTTPException) -> tuple[Union[FlaskResponse, dict], int]:
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
def not_found(error: HTTPException) -> tuple[Union[FlaskResponse, dict], int]:
    """Handle HTTP 404 Not Found errors."""
    return (
        jsonify(error="Not found", message="The requested resource was not found."),
        404,
    )


@app.errorhandler(429)
def rate_limit_exceeded(error: HTTPException) -> tuple[Union[FlaskResponse, dict], int]:
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
def internal_server_error(error: HTTPException) -> tuple[Union[FlaskResponse, dict], int]:
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
def handle_csrf_error(e: CSRFError) -> tuple[Union[FlaskResponse, dict], int]:
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
def handle_exception(e: Exception) -> tuple[Union[FlaskResponse, dict], int]:
    """Handle unhandled exceptions globally."""
    if isinstance(e, HTTPException):
        return (
            jsonify(
                error=e.name,
                message=e.description,
            ),
            e.code,
        )
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
def favicon() -> FlaskResponse:
    """Redirect favicon.ico requests to the static file with caching headers."""
    response = redirect(url_for("static", filename="favicon.ico"))
    response.headers["Cache-Control"] = "public, max-age=86400"  # Cache for 1 day
    return response


# Redirect root URL to chat interface
@app.route("/")
def index() -> FlaskResponse:
    """Redirect to login if not authenticated, otherwise to chat interface."""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"), code=307)
    return redirect(url_for("chat.chat_interface"), code=307)


# Clear session route
@app.route("/clear-session")
def clear_session() -> FlaskResponse:
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
