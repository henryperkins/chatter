import uuid
import os
import traceback
from datetime import timedelta, datetime
import platform
import sys
import psutil
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

from database import init_app, db_session, is_initialized, init_db
from extensions import limiter, login_manager, csrf
from models import User
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import chat_routes
from routes.model_routes import bp as model_bp
from routes.provider_routes import bp as provider_bp
from config import Config  # Import centralized configuration

from logging_config import get_logger

logger = get_logger(__name__)

# Load environment variables with explicit path
load_dotenv(dotenv_path="/home/azureuser/chatter/.env")

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
    # Basic configuration first
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    if not Config.DATABASE_URI:
        raise ValueError("DATABASE_URI must be set in Config")
    app.config["DATABASE_URI"] = Config.DATABASE_URI
    
    # Initialize database only once at startup
    if not is_initialized():
        try:
            logger.info("Starting database initialization...")
            with app.app_context():
                init_app(app)
                
                # Database initialization will handle default model creation
                
                if not is_initialized():
                    logger.error("Database initialization completed but is_initialized() still returns False")
                    raise RuntimeError("Database failed to initialize properly - initialization state inconsistent")
                logger.info("Database initialization completed and verified successfully")
        except Exception as e:
            logger.error("Database initialization failed with exception", exc_info=True)
            logger.error("Current app config: %s", {k: v for k, v in app.config.items() if k != 'SECRET_KEY'})
            raise RuntimeError(f"Critical error during database initialization: {str(e)}")

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
    # Database is already initialized in configure_app()

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
    app.register_blueprint(provider_bp, url_prefix="/providers")

    # Check if auth routes are properly registered
    if "auth.register" not in app.view_functions:
        logger.error("Auth routes failed to register properly")
        raise RuntimeError("Auth routes failed to register properly")

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# --- Error Handlers ---
@app.errorhandler(400)
def bad_request(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 400 Bad Request errors"""
    logger.exception(f"400 Bad Request: {request.url} - {str(error)}")
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
    logger.info(f"Resource not found: {request.url} - {str(error)}")
    return jsonify(error="Not found", message="Resource not found"), 404


@app.errorhandler(429)
def rate_limit_exceeded(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 429 Too Many Requests errors"""
    return jsonify(error="Rate limit exceeded", message="Please try again later"), 429


@app.errorhandler(500)
def internal_server_error(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    """Handle HTTP 500 Internal Server Error"""
    logger.error(f"500 Internal Server Error: {request.url} - {error} - URL: {request.url}")
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

from typing import Union, Tuple
from werkzeug.wrappers import Response as WerkzeugResponse
from typing_extensions import Literal

@app.route("/health")
def health_check() -> Union[WerkzeugResponse, Tuple[WerkzeugResponse, Literal[500]]]:
    """Health check endpoint"""
    try:
        # Basic system checks
        with db_session() as db:
            db.execute(text("SELECT 1"))  # Test database connection

        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system": {
                "python_version": sys.version,
                "platform": platform.platform(),
                "memory_usage": psutil.Process().memory_info().rss
            }
        })
    except Exception as e:
        logger.error(
            "Health check failed",
            exc_info=True,
            extra={
                "error": str(e),
                "stack_trace": traceback.format_exc(),
                "system": {
                    "memory": psutil.virtual_memory().percent,
                    "cpu": psutil.cpu_percent(),
                    "disk": psutil.disk_usage('/').percent
                }
            }
        )
        return jsonify({
            "status": "unhealthy",
            "error": "Service unavailable",
            "request_id": request.headers.get("X-Request-ID")
        }), 500

@app.route("/health/db")
def db_health_check():
    """Database health check endpoint"""
    try:
        with db_session() as db:
            db.execute(text("SELECT 1"))
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "initialized": is_initialized()
        })
    except Exception as e:
        logger.error("Database health check failed", exc_info=True)
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "initialized": is_initialized()
        }), 500


# --- User Loader ---
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user by ID"""
    try:
        with db_session() as db:
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


# --- Application Initialization ---
configure_app()
configure_security()
init_app_components()

# --- CLI Commands ---
@app.cli.command("init-db")
def init_db_command():
    """Clear existing data and create new tables."""
    try:
        logger.info("Starting database initialization...")
        with app.app_context():
            init_db()
            logger.info("Database tables created successfully")
            
            # Set up default model if none exists
            with db_session() as db:
                default_model = db.execute(
                    text("SELECT id FROM models WHERE is_default = TRUE")
                ).scalar()
                
                if not default_model:
                    logger.info("Creating default GPT-4 model configuration...")
                    model_data = {
                        "name": os.getenv("DEFAULT_MODEL_NAME", "GPT-4"),
                        "deployment_name": os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-deployment"),
                        "description": os.getenv("DEFAULT_MODEL_DESCRIPTION", "Azure GPT-4 Model"),
                        "model_type": "azure",
                        "api_endpoint": os.getenv("AZURE_API_ENDPOINT", "https://hp-east2.openai.azure.com/openai/deployments/gpt-deployment?api-version=2024-12-01-preview"),
                        "api_key": os.getenv("AZURE_API_KEY"),
                        "temperature": float(os.getenv("DEFAULT_TEMPERATURE", "0.7")),
                        "max_tokens": int(os.getenv("DEFAULT_MAX_TOKENS", "4000")),
                        "max_completion_tokens": int(os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "4000")),
                        "requires_o1_handling": True,
                        "supports_streaming": True,
                        "api_version": os.getenv("AZURE_API_VERSION", "2023-05-15"),
                        "is_default": True,
                        "version": 1
                    }
                    
                    db.execute(
                        text("""
                            INSERT INTO models (
                                name, deployment_name, description, model_type,
                                api_endpoint, api_key, temperature, max_tokens,
                                max_completion_tokens, requires_o1_handling,
                                supports_streaming, api_version, is_default, version
                            ) VALUES (
                                :name, :deployment_name, :description, :model_type,
                                :api_endpoint, :api_key, :temperature, :max_tokens,
                                :max_completion_tokens, :requires_o1_handling,
                                :supports_streaming, :api_version, :is_default, :version
                            )
                        """),
                        model_data
                    )
                    db.commit()
                    logger.info("Default model configuration created successfully")
            
            logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise

# --- Application Entry Point ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
