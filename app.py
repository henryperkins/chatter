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
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.urandom(32)

    # Session configuration
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
            "WTF_CSRF_ENABLED": True,
            "WTF_CSRF_TIME_LIMIT": 3600,
            "WTF_CSRF_SSL_STRICT": False,
            "WTF_CSRF_HEADERS": ["X-CSRFToken"],
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

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(int(user_id))

    csrf.init_app(app)
    limiter.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(chat_routes)
    app.register_blueprint(model_bp)
    app.register_blueprint(provider_bp)
    init_file_routes(app)

    app.static_folder = "static"
    app.static_url_path = "/static"


def register_cli_commands(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db_command():
        from database import init_db

        logger.info("Starting database initialization...")
        try:
            init_db()
            create_default_model(current_app)
            logger.info("Database initialization completed")
        except Exception as e:
            logger.error(f"Init failed: {e}")
            raise click.ClickException(str(e))


def create_app() -> Flask:
    if hasattr(Flask, "_already_configured"):
        return Flask._app_instance

    app = Flask(__name__)
    Flask._already_configured = True
    Flask._app_instance = app

    # Ensure config is loaded before database initialization
    config = Config()
    app.config.from_object(config)
    init_db_app(app)

    # Verify database connection
    max_retries = 3
    for attempt in range(max_retries):
        try:
            engine = app._db_state["engine"]
            if not engine:
                raise RuntimeError("Database engine not initialized")
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.scalar()
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

    register_cli_commands(app)
    return app


app = create_app()


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
    # Skip validation for static and auth endpoints
    if request.endpoint in [
        "static",
        "auth.login",
        "auth.register",
    ] or request.path.startswith("/static/"):
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
            }

        # Check system
        health_data["components"]["system"] = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "memory_usage": psutil.Process().memory_info().rss,
            "memory_percent": psutil.virtual_memory().percent,
            "cpu_percent": psutil.cpu_percent(),
            "disk_usage": psutil.disk_usage("/").percent,
        }

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
            "SEND_FILE_MAX_AGE_DEFAULT": 0 if debug_mode else 3600,
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
