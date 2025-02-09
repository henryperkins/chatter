"""Flask application main module (app.py)."""

# Load environment variables before any other imports
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=str(Path(__file__).parent / ".env"))
import logging
import click
import json
import os
import platform
import sys
import time
import traceback
import psutil
import uuid
import io
import logging
from datetime import timedelta, datetime
from typing import Optional, Tuple, Union

from flask import (
    Flask,
    jsonify,
    redirect,
    url_for,
    request,
    session,
    g,
    current_app,
    render_template,
    send_from_directory,
    make_response,
)
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from flask.cli import with_appcontext
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.wrappers import Response as WerkzeugResponse
from werkzeug.serving import WSGIRequestHandler

from sqlalchemy.orm import Session
from sqlalchemy import text
from extensions import limiter, login_manager, csrf
from config import Config, ApiError
from database import (
    init_app as init_db_app,
    db_session,
    is_initialized,
    create_default_model,
)
from models import User, Model, Provider
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import chat_routes
from routes.model_routes import bp as model_bp
from routes.provider_routes import bp as provider_bp
from routes.file_routes import init_file_routes

from logging_config import get_logger

logger = get_logger(__name__)


class SecurityMiddleware:
    """Unified security and connection header middleware."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ["HTTP_X_FORWARDED_PROTO"] = "https"
        environ["HTTP_X_FORWARDED_FOR"] = environ.get("REMOTE_ADDR", "")
        request_id = environ.get("HTTP_X_REQUEST_ID", str(uuid.uuid4()))
        environ["HTTP_X_REQUEST_ID"] = request_id

        def custom_start_response(status, headers, exc_info=None):
            security_headers = [
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "SAMEORIGIN"),
                ("X-XSS-Protection", "1; mode=block"),
                ("Connection", "keep-alive"),
            ]
            headers.extend(security_headers)
            return start_response(status, headers, exc_info)

        return self.app(environ, custom_start_response)


class UTF8RequestHandler(WSGIRequestHandler):
    """UTF-8 Request Handler with proper buffer management."""

    def handle(self):
        self.raw_requestline = self.rfile.readline()
        if not self.parse_request():
            return

        if platform.system() == "Windows":
            self.wfile = self.connection.makefile("wb", 0)
        else:
            self._binary_stream = io.BufferedWriter(
                io.FileIO(self.connection.fileno(), "wb")
            )
            self.wfile = self._binary_stream

        try:
            return super().handle()
        finally:
            self._flush_buffers()

    def _flush_buffers(self):
        try:
            if hasattr(self, "_binary_stream"):
                self._binary_stream.flush()
            elif hasattr(self, "wfile"):
                self.wfile.flush()
        except Exception:
            pass


def configure_app(app: Optional[Flask] = None) -> None:
    if app is None:
        app = current_app

    app.config.from_object(Config)
    # Explicitly set SESSION_COOKIE_DOMAIN to 'localhost' during local dev
    # if you're testing at http://localhost:5000 so cookies match the domain
    if app.config.get("ENV", "production").lower() == "development":
        app.config["SESSION_COOKIE_DOMAIN"] = "localhost"

    # Session configuration
    app.config.update(
        {
            "PERMANENT_SESSION_LIFETIME": timedelta(minutes=60),
            "SESSION_REFRESH_EACH_REQUEST": True,
            "SESSION_COOKIE_HTTPONLY": True,
            # Only force secure cookies in production; allow HTTP in dev
            "SESSION_COOKIE_SECURE": False if app.config.get("ENV") != "production" else True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_NAME": (
                "__Secure-session"
                if app.config.get("ENV") == "production"
                else "session"
            ),
            "SESSION_COOKIE_PATH": "/",
            "SESSION_COOKIE_DOMAIN": None,
            "SESSION_COOKIE_MAX_AGE": 3600,
            "SESSION_PROTECTION": "strong",
            "REMEMBER_COOKIE_SECURE": True,
            "REMEMBER_COOKIE_HTTPONLY": True,
            "REMEMBER_COOKIE_SAMESITE": "Lax",
        }
    )

    # CSRF configuration
    app.config.update(
        {
            'WTF_CSRF_ENABLED': True,
            'WTF_CSRF_SECRET_KEY': app.config['SECRET_KEY'],
            'WTF_CSRF_TIME_LIMIT': 3600,
            'WTF_CSRF_SSL_STRICT': False,
            'WTF_CSRF_HEADERS': ['X-CSRFToken', 'X-CSRF-Token'],
            'WTF_CSRF_METHODS': ['POST', 'PUT', 'PATCH', 'DELETE'],
            'WTF_CSRF_FIELD_NAME': 'csrf_token',
            'WTF_CSRF_CHECK_DEFAULT': True  # Enable CSRF for all routes by default
        }
    )

    # Upload folder configuration
    if not app.config.get("UPLOAD_FOLDER"):
        app.config["UPLOAD_FOLDER"] = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "uploads"
        )
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.chmod(app.config["UPLOAD_FOLDER"], 0o755)


def init_app_components(app: Flask) -> None:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.wsgi_app = SecurityMiddleware(app.wsgi_app)

    # Initialize CSRF protection first
    csrf.init_app(app)
    csrf.exempt(app.static_folder)
    
    # Then initialize login manager
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # type: ignore

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(int(user_id))

    # Initialize rate limiter
    limiter.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(chat_routes)
    app.register_blueprint(model_bp)
    app.register_blueprint(provider_bp)
    init_file_routes(app)

    app.static_folder = "static"
    app.static_url_path = "/static"

    # Configure static file MIME types
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 if app.config.get('DEBUG', False) else 3600

    @app.route('/static/<path:filename>')
    def serve_static(filename):
        mimetype = None
        if filename.endswith('.css'):
            mimetype = 'text/css'
        elif filename.endswith('.js'):
            mimetype = 'application/javascript'
        return send_from_directory(str(app.static_folder), filename, mimetype=mimetype)


def register_cli_commands(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db_command():
        from database import init_db

        logger.info("Starting database initialization...")
        try:
            init_db()
            with db_session() as db:
                create_default_model(db)
            logger.info("Database initialization completed")
        except Exception as e:
            logger.error(f"Init failed: {e}")
            raise click.ClickException(str(e))

    @app.cli.command("check-model")
    def check_model_command():
        """Check model configuration in database."""
        try:
            with db_session() as db:
                result = db.execute(text("""
                    SELECT
                        m.id as model_id,
                        m.name as model_name,
                        m.deployment_name,
                        m.api_endpoint,
                        LENGTH(m.api_key) as api_key_length,
                        m.api_version,
                        p.name as provider_name,
                        p.slug as provider_slug,
                        p.api_base_url,
                        p.is_azure
                    FROM models m
                    JOIN providers p ON m.provider_id = p.id
                    WHERE m.is_default = true;
                """)).mappings().first()

                if result:
                    print("\nModel Configuration:")
                    print("-" * 50)
                    for key, value in result.items():
                        print(f"{key}: {value}")
                else:
                    print("\nNo default model found!")
        except Exception as e:
            print(f"Error checking model: {str(e)}")

    @app.cli.command("check-model-details")
    def check_model_details_command():
        """Check detailed model configuration in database."""
        try:
            with db_session() as db:
                # Get model details
                result = db.execute(text("""
                    SELECT
                        m.id as model_id,
                        m.name as model_name,
                        m.deployment_name,
                        m.api_endpoint,
                        LENGTH(m.api_key) as api_key_length,
                        m.api_version,
                        p.name as provider_name,
                        p.slug as provider_slug,
                        p.api_base_url,
                        p.is_azure,
                        m.api_key as encrypted_key
                    FROM models m
                    JOIN providers p ON m.provider_id = p.id
                    WHERE m.is_default = true;
                """)).mappings().first()

                if result:
                    print("\nModel Configuration:")
                    print("-" * 50)
                    for key, value in result.items():
                        if key != 'encrypted_key':  # Don't print the actual encrypted key
                            print(f"{key}: {value}")

                    # Test decryption
                    if result['encrypted_key']:
                        from config import Config
                        from utils.encryption import decrypt_api_key
                        import base64
                        import hashlib

                        config_instance = Config()
                        key_bytes = hashlib.sha256(config_instance.ENCRYPTION_KEY.encode()).digest()
                        encryption_key = base64.b64encode(key_bytes).decode()

                        try:
                            decrypted_key = decrypt_api_key(result['encrypted_key'], encryption_key)
                            print(f"\nAPI Key decryption test: {'SUCCESS' if decrypted_key else 'FAILED'}")
                            print(f"Decrypted key length: {len(decrypted_key) if decrypted_key else 0}")
                        except Exception as e:
                            print(f"\nAPI Key decryption error: {str(e)}")
                else:
                    print("\nNo default model found!")
        except Exception as e:
            print(f"Error checking model: {str(e)}")

    @app.cli.command("fix-deployment-name")
    def fix_deployment_name_command():
        """Fix the deployment name typo."""
        try:
            with db_session() as db:
                query = text("""
                    UPDATE models
                    SET deployment_name = 'gpt-deployment'
                    WHERE deployment_name = 'gpt-deploymente'
                    RETURNING id
                """)
                result = db.execute(query)
                db.commit()
                if result.rowcount > 0:  # type: ignore
                    print("Successfully fixed deployment name")
                else:
                    print("No models needed fixing")
        except Exception as e:
            print(f"Error fixing deployment name: {str(e)}")


def create_app() -> Flask:
    if hasattr(Flask, "_already_configured"):
        return Flask._app_instance  # type: ignore

    app = Flask(__name__)
    Flask._already_configured = True  # type: ignore
    Flask._app_instance = app  # type: ignore

    # Ensure config is loaded before database initialization
    config = Config()
    app.config.from_object(config)

    # Debug log the current environment
    import sys
    print(f"DEBUG: app.config['ENV'] -> {app.config['ENV']}", file=sys.stderr)
    print(f"DEBUG: app.config['DEBUG'] -> {app.config['DEBUG']}", file=sys.stderr)
    print(f"DEBUG: ENV: {app.config['ENV']}", file=sys.stderr)
    print(f"DEBUG: DEBUG: {app.config['DEBUG']}", file=sys.stderr)

    init_db_app(app)

    # Verify database connection
    max_retries = 3
    for attempt in range(max_retries):
        try:
            engine = app._db_state["engine"]  # type: ignore
            if not engine:
                raise RuntimeError("Database engine not initialized")
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.scalar()
            if not app._db_state.get("Session"):  # type: ignore
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
            app._components_initialized = True  # type: ignore
        except Exception as e:
            logger.error("Component initialization failed", exc_info=True)
            raise RuntimeError(
                f"Critical error during component initialization: {str(e)}"
            )

    register_cli_commands(app)
    return app



def create_error_response(
    error_msg: str, status_code: int
) -> Tuple[WerkzeugResponse, int]:
    return (
        jsonify(
            error=error_msg,
            message="An error occurred",
            request_id=getattr(g, "request_id", None),
        ),
        status_code,
    )

app = create_app()

# Error handlers
for code in [400, 401, 403, 404, 405, 429]:
    app.errorhandler(code)(lambda e, c=code: create_error_response(str(e), c))


@app.errorhandler(500)
def internal_server_error(error: HTTPException) -> Tuple[WerkzeugResponse, int]:
    logger.error(f"500 Internal Server Error: {request.url} - {error}")
    return create_error_response("Internal server error", 500)


@app.errorhandler(Exception)
def handle_exception(e):
    if request.path.startswith("/static/"):
        raise e
    logger.exception(
        "Unhandled exception occurred - URL: %s, Method: %s, User: %s, Error: %s",
        request.url,
        request.method,
        current_user.id if current_user.is_authenticated else "anonymous",
        str(e),
    )
    if app.config.get("ENV") == "production":
        return create_error_response("Internal server error", 500)
    return create_error_response(str(e), 500)


@app.errorhandler(CSRFError)
def handle_csrf_error(e: CSRFError) -> Tuple[WerkzeugResponse, int]:
    return create_error_response("Invalid CSRF token", 400)


@app.before_request
def validate_request():
    logger.debug("Processing request: %s %s", request.method, request.path)
    # Skip validation for static and auth endpoints
    if request.endpoint in [
        "static",
        "auth.login"
    ] or request.path.startswith("/static/"):
        logger.debug("Skipping validation for endpoint: %s", request.endpoint)
        return

    # Set request context
    g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    g.user_id = current_user.id if current_user.is_authenticated else "anonymous"

    # Debounce check
    if request.endpoint:
        key = f"{request.remote_addr}:{request.endpoint}"
        timestamps = getattr(g, "_request_timestamps", {})
        last_request = timestamps.get(key, 0)
        current_time = time.time()
        if current_time - last_request < 0.1:
            return create_error_response("Too many requests", 429)
        timestamps[key] = current_time
        g._request_timestamps = timestamps

    # Session validation
    if current_user.is_authenticated:
        try:
            fresh_user = User.get_by_id(current_user.id)
            if not fresh_user or not fresh_user.is_active:
                logout_user()
                session.clear()
                return redirect(url_for("auth.login"))
            session["last_active"] = datetime.now().isoformat()
            session.modified = True
        except Exception as e:
            logger.error("Session validation error: %s", str(e))
            logout_user()
            session.clear()
            return redirect(url_for("auth.login"))


@app.teardown_request
def cleanup_request(exception=None):
    # Custom cleanup logic
    cleanup_attrs = [
        "_db_session_instance",
        "_request_timestamps",
        "_request_logged",
        "correlation_id",
        "request_id",
        "user_id",
    ]
    # Optionally perform other cleanup tasks here (e.g. closing sessions via db_session)
    for attr in cleanup_attrs:
        if hasattr(g, attr):
            if attr == "_db_session_instance":
                try:
                    g._db_session_instance.close()
                except Exception:
                    pass
            delattr(g, attr)


@app.route("/favicon.ico")
def favicon() -> WerkzeugResponse:
    return redirect(url_for("static", filename="favicon.ico"))


@app.route("/", methods=["GET", "POST"])
def index() -> WerkzeugResponse:
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("chat.chat_interface"))

    # Add an explicit route to handle requests to "/login" in case they are arriving here instead of "/auth/login"
    @app.route("/login", methods=["GET", "POST"])
    def direct_login():
        # Redirect to the actual auth.login route
        return redirect(url_for("auth.login"))

@app.route("/clear-session")
def clear_session() -> WerkzeugResponse:
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@app.route("/health")
def health_check():
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {},
    }

    try:
        # Check database
        with db_session() as db:
            db.query(Model).count()
            with db.begin():
                pass
            health_data["components"]["database"] = {
                "status": "healthy",
                "initialized": is_initialized(),
                "read_write": "success",
            }  # type: ignore

        # Check system
        health_data["components"]["system"] = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "memory_usage": psutil.Process().memory_info().rss,
            "memory_percent": psutil.virtual_memory().percent,
            "cpu_percent": psutil.cpu_percent(),
            "disk_usage": psutil.disk_usage("/").percent,
        }  # type: ignore

        return jsonify(health_data)

    except Exception as e:
        logger.error("Health check failed", exc_info=True)
        return create_error_response("Service unavailable", 500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    debug_mode = app.config["DEBUG"]

    app.config.update(
        {
            "DEBUG": debug_mode,
            "TEMPLATES_AUTO_RELOAD": debug_mode,
            "SEND_FILE_MAX_AGE_DEFAULT": 0 if debug_mode else 3600,  # type: ignore
        }
    )

    if debug_mode:
        logger.warning("Debug mode is enabled - not recommended for production")
        app.config.update(
            {"DEBUG_TB_ENABLED": False, "DEBUG_TB_INTERCEPT_REDIRECTS": False}
        )

    logger.info(f"Starting application on {host}:{port}")
    from werkzeug.serving import run_simple

    run_simple(
        host,
        port,
        app,
        use_debugger=app.config["DEBUG"],
        request_handler=UTF8RequestHandler,
    )
