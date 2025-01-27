"""Flask application main module."""

import logging
from logging import Logger
import click
import json
import os
import platform
import sys
import time
import traceback
import psutil
import uuid
from datetime import timedelta, datetime
from typing import Optional, Tuple, Union

# Configure logging before importing other modules that might log messages
logger = logging.getLogger(__name__)

from flask import Flask, jsonify, redirect, url_for, request, session, g, current_app
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from flask.cli import with_appcontext
from dotenv import load_dotenv

# Security / HTTP
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.wrappers import Response as WerkzeugResponse

# Database & ORM
from sqlalchemy import text
from sqlalchemy.orm import Session

# Rate limiting and other extensions
from extensions import limiter, login_manager, csrf

# Local modules
from config import Config  # Centralized configuration
from database import (
    init_app as init_db_app,  # So we don't confuse with init_db
    db_session,
    db_transaction,
    is_initialized,
    get_db_state,
)
from models import User, Model, Provider
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import chat_routes
from routes.model_routes import bp as model_bp
from routes.provider_routes import bp as provider_bp



class ConnectionHeaderMiddleware:
    """
    Middleware to handle connection headers and improve request handling.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Add custom headers to the request
        environ["HTTP_X_FORWARDED_PROTO"] = "https"  # Force HTTPS
        environ["HTTP_X_FORWARDED_FOR"] = environ.get("REMOTE_ADDR", "")

        # Add request ID for tracing
        request_id = environ.get("HTTP_X_REQUEST_ID", str(uuid.uuid4()))
        environ["HTTP_X_REQUEST_ID"] = request_id

        # Log basic request details without request context
        logger.debug(
            "Incoming request - Method: %s, Path: %s, Remote: %s",
            environ.get("REQUEST_METHOD", ""),
            environ.get("PATH_INFO", ""),
            environ.get("REMOTE_ADDR", ""),
            extra={"request_id": request_id},
        )

        # Call the next middleware/app
        return self.app(environ, start_response)


def get_azure_provider_id(db: Session) -> int:
    """Get or create the Azure provider ID using the provided session"""
    from models.provider import Provider  # Add import

    # Try to get existing provider first using current session
    try:
        with db.begin_nested():  # Explicit transaction
            result = db.execute(
                text("SELECT id FROM providers WHERE slug = :slug"),
                {"slug": "azure-openai"},
            )
            provider_id = result.scalar_one_or_none()

            if provider_id:
                return provider_id

            # Create new provider using direct SQL to stay in same transaction
            result = db.execute(
                text(
                    """
                    INSERT INTO providers (
                        name, slug, api_base_url, capabilities,
                        requires_authentication, api_version_format,
                        endpoint_pattern, auth_type, validation_rules
                    ) VALUES (
                        :name, :slug, :api_base_url, :capabilities,
                        :requires_authentication, :api_version_format,
                        :endpoint_pattern, :auth_type, :validation_rules
                    )
                    RETURNING id
                """
                ),
                {
                    "name": "Azure OpenAI",
                    "slug": "azure-openai",
                    "api_base_url": Config.AZURE_API_ENDPOINT.rstrip("/"),
                    "capabilities": json.dumps(
                        {
                            "azure": {
                                "supports_streaming": True,
                                "max_tokens": 16384,
                                "token_overhead": 3,
                                "endpoint_format": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
                                "api_version": "2024-12-01-preview",
                            },
                            "o1-preview": {
                                "fixed_temperature": True,
                                "streaming": False,
                                "max_tokens": 8300,
                                "token_overhead": 3,
                                "endpoint_format": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
                                "api_version": "2024-12-01-preview",
                            },
                        }
                    ),
                    "requires_authentication": True,
                    "api_version_format": "2024-12-01-preview",
                    "endpoint_pattern": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
                    "auth_type": "api-key",
                    "validation_rules": json.dumps(
                        {
                            "model_id": "^[a-zA-Z0-9-]{3,64}$",
                            "api_version": "^\\d{4}-\\d{2}-\\d{2}(-preview)?$",
                        }
                    ),
                },
            )
            provider_id = result.scalar_one()
    except Exception as e:
        raise

    if not provider_id:
        raise ValueError("Failed to create Azure provider")

    return provider_id


def initialize_default_model(app):
    """Create default Azure OpenAI provider and model using app config"""
    try:
        with db_session(app) as db:
            # Check if default already exists
            if db.execute(
                text("SELECT 1 FROM models WHERE is_default = TRUE")
            ).scalar():
                logger.info("Default model already exists")
                return

            # Create provider and model - transaction is managed by db_session
            provider_data = {
                "name": "Azure OpenAI",
                "slug": "azure-openai",
                "api_base_url": Config.AZURE_API_ENDPOINT.rstrip("/"),
                "api_version_format": "YYYY-MM-DD",
                "auth_type": "api-key",
                "endpoint_pattern": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
                "validation_rules": {
                    "model_id": "^[a-zA-Z0-9-]{3,64}$",
                    "api_version": "^\\d{4}-\\d{2}-\\d{2}(-preview)?$",
                },
                "capabilities": {
                    "azure": {
                        "supports_streaming": True,
                        "max_tokens": 16384,
                        "token_overhead": 3,
                    },
                    "o1-preview": {
                        "fixed_temperature": True,
                        "streaming": False,
                        "max_tokens": 8300,
                        "token_overhead": 3,
                    },
                },
                "requires_authentication": True,
            }

            # Insert provider and get ID in same transaction
            provider_id = db.execute(
                text(
                    """
                    INSERT INTO providers (
                        name, slug, api_base_url, capabilities,
                        requires_authentication, api_version_format,
                        endpoint_pattern, auth_type, validation_rules
                    ) VALUES (
                        :name, :slug, :api_base_url, :capabilities,
                        :requires_authentication, :api_version_format,
                        :endpoint_pattern, :auth_type, :validation_rules
                    )
                    RETURNING id
                """
                ),
                {
                    **provider_data,
                    "capabilities": json.dumps(provider_data["capabilities"]),
                    "validation_rules": json.dumps(provider_data["validation_rules"]),
                },
            ).scalar_one()

            if not provider_id:
                raise ValueError("Failed to create Azure OpenAI provider")

            # Create default model using the same transaction
            model_data = {
                "provider_id": provider_id,
                "name": Config.DEFAULT_MODEL_NAME,
                "deployment_name": Config.DEFAULT_DEPLOYMENT_NAME,
                "description": Config.DEFAULT_MODEL_DESCRIPTION,
                "api_endpoint": Config.DEFAULT_API_ENDPOINT,
                "api_key": Config.AZURE_API_KEY,
                "model_type": "azure",
                "temperature": Config.DEFAULT_TEMPERATURE,
                "max_tokens": Config.DEFAULT_MAX_TOKENS,
                "max_completion_tokens": Config.DEFAULT_MAX_COMPLETION_TOKENS,
                "requires_o1_handling": Config.DEFAULT_REQUIRES_O1_HANDLING,
                "supports_streaming": Config.DEFAULT_SUPPORTS_STREAMING,
                "is_default": True,
                "api_version": Config.DEFAULT_API_VERSION,
            }

            # Insert model in same transaction
            model_id = db.execute(
                text(
                    """
                    INSERT INTO models (
                        provider_id, name, deployment_name, description, api_endpoint, api_key,
                        api_version, temperature, max_tokens, max_completion_tokens,
                        model_type, requires_o1_handling, supports_streaming, is_default
                    ) VALUES (
                        :provider_id, :name, :deployment_name, :description, :api_endpoint, :api_key,
                        :api_version, :temperature, :max_tokens, :max_completion_tokens,
                        :model_type, :requires_o1_handling, :supports_streaming, :is_default
                    )
                    RETURNING id
                """
                ),
                model_data,
            ).scalar_one()

            if not model_id:
                raise ValueError("Failed to create default model")

            logger.info(
                "Azure OpenAI provider and default model initialized successfully"
            )
    except Exception as e:
        logger.error(f"Default model initialization failed: {str(e)}")
        raise


# --------------------------------------------------------------
#  CLI Commands
# --------------------------------------------------------------
# --------------------------------------------------------------
#  Flask App Configuration
# --------------------------------------------------------------
def configure_app(app: Optional[Flask] = None) -> None:
    """
    Configure Flask application settings.
    """
    if app is None:
        app = current_app

    # Load environment variables from .env
    load_dotenv()

    # Load config from Config class
    app.config.from_object(Config)

    # Set secret key
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(32))

    # Database URI configuration with validation
    def build_database_uri():
        if uri := os.getenv("DATABASE_URI"):
            return uri

        required_params = {
            "DB_USER": os.getenv("DB_USER", "postgres"),
            "DB_PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
            "DB_HOST": os.getenv("DB_HOST", "localhost"),
            "DB_PORT": os.getenv("DB_PORT", "5432"),
            "DB_NAME": os.getenv("DB_NAME", "chatter"),
        }

        # Validate port number
        try:
            port = int(required_params["DB_PORT"])
            if not (1024 <= port <= 65535):
                raise ValueError(f"Invalid port number: {port}")
        except ValueError as e:
            logger.error(f"Database configuration error: {str(e)}")
            raise RuntimeError(f"Invalid database port configuration: {str(e)}")

        return (
            f"postgresql://{required_params['DB_USER']}:"
            f"{required_params['DB_PASSWORD']}@"
            f"{required_params['DB_HOST']}:"
            f"{required_params['DB_PORT']}/"
            f"{required_params['DB_NAME']}"
        )

    try:
        app.config["DATABASE_URI"] = build_database_uri()
        logger.info("Database URI configured successfully")
    except Exception as e:
        logger.error(f"Failed to configure database URI: {str(e)}")
        raise RuntimeError(f"Database configuration failed: {str(e)}")

    # Database connection settings
    app.config.update(
        {
            "SQLALCHEMY_POOL_SIZE": int(os.getenv("DB_POOL_SIZE", "5")),
            "SQLALCHEMY_POOL_TIMEOUT": int(os.getenv("DB_POOL_TIMEOUT", "30")),
            "SQLALCHEMY_POOL_RECYCLE": int(os.getenv("DB_POOL_RECYCLE", "1800")),
            "SQLALCHEMY_MAX_OVERFLOW": int(os.getenv("DB_MAX_OVERFLOW", "10")),
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "pool_pre_ping": True,
                "pool_use_lifo": True,
                "connect_args": {
                    "connect_timeout": 10,
                    "options": "-c statement_timeout=30000 -c default_transaction_isolation='read committed'",
                },
            },
        }
    )

    # Enhanced session settings
    app.config.update(
        {
            "PERMANENT_SESSION_LIFETIME": timedelta(minutes=60),
            "SESSION_REFRESH_EACH_REQUEST": True,
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SECURE": app.config.get("ENV") == "production",
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_NAME": (
                "__Secure-session"
                if app.config.get("ENV") == "production"
                else "session"
            ),
            "SESSION_COOKIE_PATH": "/",
            "SESSION_COOKIE_DOMAIN": None,
            "SESSION_COOKIE_MAX_AGE": 3600,  # 1 hour in seconds
            "SESSION_PROTECTION": "strong",  # Prevent session fixation
            "REMEMBER_COOKIE_SECURE": True,
            "REMEMBER_COOKIE_HTTPONLY": True,
            "REMEMBER_COOKIE_SAMESITE": "Lax",
        }
    )

    # Security settings
    app.config.update(
        {
            "WTF_CSRF_ENABLED": True,
            "WTF_CSRF_TIME_LIMIT": 3600,
            "WTF_CSRF_SSL_STRICT": False,
            "WTF_CSRF_HEADERS": ["X-CSRFToken"],
        }
    )

    # Ensure UPLOAD_FOLDER exists
    if not app.config.get("UPLOAD_FOLDER"):
        app.config["UPLOAD_FOLDER"] = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "uploads"
        )
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.chmod(app.config["UPLOAD_FOLDER"], 0o755)

    return app


# --------------------------------------------------------------
#  CLI Commands (Registered AFTER app creation)
# --------------------------------------------------------------
def register_cli_commands(app):
    """Register CLI commands with the Flask application."""

    @app.cli.command("init-db")
    @with_appcontext
    def init_db_command():
        """Create tables and seed initial data"""
        from database import init_db

        logger.info("Starting database initialization...")
        try:
            # 1. Create tables
            init_db()

            # 2. Create default model
            initialize_default_model(current_app)

            # 3. Create admin user in same transaction
            with db_session(current_app) as db:
                if db.execute(text("SELECT COUNT(*) FROM users")).scalar() == 0:
                    from werkzeug.security import generate_password_hash

                    db.execute(
                        text(
                            """
                            INSERT INTO users 
                            (username, email, password_hash, role)
                            VALUES ('admin', 'admin@example.com', :hash, 'admin')
                        """
                        ),
                        {"hash": generate_password_hash("admin")},
                    )
                    db.commit()
                    logger.info("Created default admin user")

            logger.info("Database initialization completed")

        except Exception as e:
            logger.error(f"Init failed: {e}")
            raise click.ClickException(str(e))


# --------------------------------------------------------------
#  Initialize Extensions and Register Blueprints
# --------------------------------------------------------------
def init_app_components(app: Flask) -> None:
    """Initialize Flask extensions and register blueprints."""
    # Apply Reverse Proxy Fix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Initialize connection header middleware
    app.wsgi_app = ConnectionHeaderMiddleware(app.wsgi_app)

    # Initialize extensions
    from models.user import User  # Import here to avoid circular imports

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(int(user_id))

    csrf.init_app(app)
    limiter.init_app(app)

    # Verify extensions are properly initialized
    if not login_manager.user_loader:
        raise RuntimeError("Login manager user loader not configured")

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(chat_routes, url_prefix="/")
    app.register_blueprint(model_bp, url_prefix="/models")
    app.register_blueprint(provider_bp, url_prefix="/providers")

    # Debug: Print all registered routes
    print("Registered routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule}")

    # Ensure auth routes are registered
    if "auth.login" not in app.view_functions:
        logger.error("Auth routes failed to register properly.")
        raise RuntimeError("Auth routes failed to register properly.")


# --------------------------------------------------------------
#  Application Factory
# --------------------------------------------------------------
def create_app() -> Flask:
    """Application factory function."""
    if hasattr(Flask, "_already_configured"):
        return Flask._app_instance

    app = Flask(__name__)
    Flask._already_configured = True
    Flask._app_instance = app
    configure_app(app)

    # Initialize database with explicit app binding
    init_db_app(app)  # This now sets app._db_state directly

    # Verify connection using app's own state
    max_retries = 3
    for attempt in range(max_retries):
        try:
            engine = app._db_state["engine"]
            if not engine:
                raise RuntimeError("Database engine not initialized")

            with engine.connect() as conn:
                # Execute validation query without transaction management
                result = conn.execute(text("SELECT 1"))
                result.close()  # Explicitly close result
                conn.commit()  # Commit any implicit transaction
            logger.debug("Database connection verified")

            # Validate session factory
            if not app._db_state.get("Session"):
                raise RuntimeError("Database session factory not initialized")

            break
        except Exception as e:
            if attempt == max_retries - 1:
                logger.critical("Database connection failed after retries")
                raise RuntimeError(f"Database connection failed: {str(e)}")
            time.sleep(0.5 * (attempt + 1))

    if not hasattr(app, "_components_initialized"):
        try:
            init_app_components(app)
            app._components_initialized = True
        except Exception as e:
            logger.error("Component initialization failed", exc_info=True)
            raise RuntimeError(
                f"Critical error during component initialization: {str(e)}"
            )

    # Register CLI commands before returning app
    register_cli_commands(app)

    return app


# --------------------------------------------------------------
#  Create the main application instance
# --------------------------------------------------------------


app = create_app()


# --------------------------------------------------------------
#  Error Handlers
# --------------------------------------------------------------
@app.errorhandler(400)
def bad_request(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    logger.exception(f"400 Bad Request: {request.url} - {str(error)}")
    return (
        jsonify(error="Bad request", message=error.description or "Invalid request"),
        400,
    )


@app.errorhandler(401)
def unauthorized(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    logger.warning(f"Unauthorized access attempt: {str(error)}")
    return (
        jsonify(error="Unauthorized", message="Please login to access this resource"),
        401,
    )


@app.errorhandler(403)
def forbidden(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    logger.warning(f"Forbidden access attempt: {str(error)}")
    return jsonify(error="Forbidden", message="Access denied"), 403


@app.errorhandler(404)
def not_found(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    logger.info(f"Resource not found: {request.url} - {str(error)}")
    return jsonify(error="Not found", message="Resource not found"), 404


@app.errorhandler(405)
def method_not_allowed(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    logger.warning(f"Method not allowed: {request.method} {request.url}")
    return (
        jsonify(
            error="Method not allowed",
            message=f"The {request.method} method is not supported for this endpoint",
        ),
        405,
    )


@app.errorhandler(429)
def rate_limit_exceeded(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    return (
        jsonify(error="Rate limit exceeded", message="Please try again later"),
        429,
    )


@app.errorhandler(500)
def internal_server_error(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    logger.error(f"500 Internal Server Error: {request.url} - {error}")
    return (
        jsonify(error="Internal server error", message="An unexpected error occurred"),
        500,
    )


@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all for uncaught exceptions."""
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
        return (
            jsonify(error="Internal server error", message="Please try again later"),
            500,
        )
    else:
        return jsonify(error="Internal server error", message=str(e)), 500


@app.errorhandler(CSRFError)
def handle_csrf_error(e: CSRFError) -> Tuple[WerkzeugResponse, int]:
    return (
        jsonify(error="Invalid CSRF token", message="Please refresh and try again"),
        400,
    )


# --------------------------------------------------------------
#  Request Hooks
# --------------------------------------------------------------
def startup_message():
    """Log application startup information"""
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" and not app.debug:
        logger = logging.getLogger("app.startup")
        logger.info("Application startup completed")
        logger.info(
            f"Listening on {app.config.get('HOST', '0.0.0.0')}:{app.config.get('PORT', 5000)}"
        )
        if app.config.get("DEBUG"):
            logger.warning("Debug mode is enabled - not recommended for production")


# Call startup_message when app is ready
startup_message()


@app.before_request
def debounce_requests():
    """Prevent rapid repeated requests from the same client"""
    if request.endpoint and "static" not in request.endpoint:
        client_id = request.remote_addr
        endpoint = request.endpoint
        key = f"{client_id}:{endpoint}"

        # Use thread-local storage for request tracking
        if not hasattr(g, "_request_timestamps"):
            g._request_timestamps = {}

        last_request = g._request_timestamps.get(key)
        current_time = time.time()

        if (
            last_request and (current_time - last_request) < 0.1
        ):  # 100ms minimum between requests
            return jsonify({"error": "Too many requests"}), 429

        g._request_timestamps[key] = current_time


@app.before_request
def set_logging_context():
    """Set logging context for each request."""
    g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    g.user_id = current_user.id if current_user.is_authenticated else "anonymous"

    # Use logging adapter instead of modifying formatters
    logger = logging.getLogger()
    logger = logging.LoggerAdapter(
        logger, {"request_id": g.request_id, "user_id": g.user_id}
    )

    logger.debug(
        "Request received - Method: %s, Path: %s, Remote: %s",
        request.method,
        request.path,
        request.remote_addr,
    )


@app.before_request
def validate_user_session():
    """Centralized session validation"""
    if request.endpoint in [
        "static",
        "auth.login",
        "auth.register",
    ] or request.path.startswith("/static/"):
        return

    if current_user.is_authenticated:
        try:
            # Use User model's verification method
            fresh_user = User.get_by_id(current_user.id)
            if not fresh_user or not fresh_user.is_active:
                logger.info(f"Invalid session for user {current_user.id}")
                logout_user()
                session.clear()
                return redirect(url_for("auth.login"))

            # Update session timestamp
            session["last_active"] = datetime.now().isoformat()
            session.modified = True

        except Exception as e:
            logger.error("Error validating user session: %s", str(e), exc_info=True)
            # On error, clear session for safety
            logout_user()
            session.clear()
            return redirect(url_for("auth.login"))


# --------------------------------------------------------------
#  Teardown Hooks
# --------------------------------------------------------------
@app.teardown_request
def cleanup_request(exception=None):
    """Clean up request context."""
    try:
        # Clear any session in flask.g
        if hasattr(g, "_db_session_instance"):
            delattr(g, "_db_session_instance")

        # Clear request-specific attributes
        if hasattr(g, "_request_logged"):
            delattr(g, "_request_logged")

        # Clean up correlation ID
        if hasattr(g, "correlation_id"):
            delattr(g, "correlation_id")

    except Exception as e:
        logger.error(f"Error during request cleanup: {str(e)}")


@app.teardown_appcontext
def cleanup_context(exception=None):
    """Clean up application context."""
    try:
        # Ensure db session is removed
        if hasattr(g, "_db_session_instance"):
            delattr(g, "_db_session_instance")
    except Exception as e:
        logger.error(f"Error during context cleanup: {str(e)}")


# --------------------------------------------------------------
#  Routes
# --------------------------------------------------------------
@app.route("/favicon.ico")
def favicon() -> WerkzeugResponse:
    """Serve favicon requests by redirecting to static/favicon.ico."""
    return redirect(url_for("static", filename="favicon.ico"))


@app.route("/")
def index() -> WerkzeugResponse:
    """Root endpoint."""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("chat.chat_interface"))


@app.route("/clear-session")
def clear_session() -> WerkzeugResponse:
    """Manually clear user session."""
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------
#  Health Check Endpoints
# --------------------------------------------------------------
@app.route("/health")
def health_check() -> Union[WerkzeugResponse, Tuple[WerkzeugResponse, int]]:
    """Basic health check endpoint."""
    try:
        # Check DB connectivity
        with db_session() as db:
            # Execute validation query without transaction management
            result = db.execute(text("SELECT 1"))
            result.close()  # Explicitly close result
            db.commit()  # Commit any implicit transaction

        return jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "system": {
                    "python_version": sys.version,
                    "platform": platform.platform(),
                    "memory_usage": psutil.Process().memory_info().rss,
                },
            }
        )
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
                    "disk": psutil.disk_usage("/").percent,
                },
            },
        )
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": "Service unavailable",
                    "request_id": request.headers.get("X-Request-ID"),
                }
            ),
            500,
        )


@app.route("/health/db")
def db_health_check():
    """Database-specific health check endpoint."""
    try:
        with db_session() as db:
            # Execute validation query without transaction management
            result = db.execute(text("SELECT 1"))
            result.close()

            # Test read/write operations in explicit transaction
            with db.begin():
                test_id = db.execute(
                    text("INSERT INTO test_table (value) VALUES ('test') RETURNING id")
                ).scalar()
                if test_id:
                    db.execute(
                        text("DELETE FROM test_table WHERE id = :id"), {"id": test_id}
                    )

        return jsonify(
            {
                "status": "healthy",
                "database": "connected",
                "initialized": is_initialized(),
                "read_write": "success",
            }
        )
    except Exception as e:
        logger.error("Database health check failed", exc_info=True)
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "initialized": is_initialized(),
                    "read_write": "failed",
                }
            ),
            500,
        )


# --------------------------------------------------------------
#  Main Entry Point (Development Only)
# --------------------------------------------------------------


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    # Set debug mode based on environment
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
    app.config["DEBUG"] = debug_mode
    app.config["TEMPLATES_AUTO_RELOAD"] = debug_mode
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0 if debug_mode else 3600

    if debug_mode:
        logger.warning("Debug mode is enabled - not recommended for production")
        # Disable debugger pin for security
        app.config["DEBUG_TB_ENABLED"] = False
        app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False

    logger.info(f"Starting application on {host}:{port}")
    # For production, do NOT use app.run(debug=True). Instead, use a WSGI server (gunicorn, uwsgi, etc.)
    app.run(host=host, port=port, debug=app.config["DEBUG"])
