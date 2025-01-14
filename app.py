import os
import ssl
import logging
import redis
from datetime import timedelta
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, url_for, request, session, g
import uuid
from flask_login import current_user, logout_user
from flask_talisman import Talisman
from flask_sslify import SSLify
from flask_wtf.csrf import CSRFError
from werkzeug.wrappers import Response
from werkzeug.exceptions import HTTPException
from sqlalchemy import text
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from database import close_db, init_db, init_app, get_db

# Initialize logger
logger = logging.getLogger(__name__)
from models import User, Model
from extensions import limiter, login_manager, csrf
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import chat_routes
from routes.model_routes import bp as model_bp

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Middleware to handle Connection: Upgrade header
class RemoveConnectionUpgradeMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Check if 'Connection' header exists and contains 'Upgrade'
        connection_header = environ.get('HTTP_CONNECTION', '')
        if 'upgrade' in connection_header.lower():
            # Remove 'Upgrade' from the 'Connection' header
            environ['HTTP_CONNECTION'] = 'close'
            logger.debug(f"Modified Connection header from '{connection_header}' to 'close'")
        return self.app(environ, start_response)

# Wrap the Flask app with the middleware
app.wsgi_app = RemoveConnectionUpgradeMiddleware(app.wsgi_app)

# Configure Flask-Limiter to use Redis
limiter.init_app(app)

# --- Configuration Functions ---
def configure_ssl() -> ssl.SSLContext:
    """Configure SSL context with secure defaults"""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256')
    return context

def configure_security() -> None:
    """Configure security settings"""
    if not app.testing:
        # Enable HTTPS
        SSLify(app)
        
        # Security headers with Talisman
        Talisman(app, content_security_policy={
            'default-src': "'self'",
            'script-src': "'self' 'unsafe-inline'",
            'style-src': "'self' 'unsafe-inline' 'self' 'unsafe-inline' 'style-src-elem'",
            'img-src': "'self' data:",
            'connect-src': "'self'",
            'font-src': "'self'",
            'object-src': "'none'",
            'frame-src': "'none'"
        })
        
        # Secure cookie settings
        app.config.update(
            SESSION_COOKIE_SECURE=True,
            REMEMBER_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            REMEMBER_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax',
            PREFERRED_URL_SCHEME='https'
        )

def configure_app() -> None:
    """Configure Flask application settings"""
    # Basic configuration
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["DATABASE"] = os.environ.get("DATABASE", "chat_app.db")
    
    # File upload settings
    app.config.update(
        UPLOAD_FOLDER=os.path.join(app.root_path, "uploads"),
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MB
        MAX_FILE_SIZE=10 * 1024 * 1024,  # 10 MB
        MAX_FILES=5,
        MAX_MESSAGE_LENGTH=1000,
        ALLOWED_FILE_TYPES=["text/plain", "application/pdf", "image/jpeg", "image/png"]
    )
    
    # Session settings
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),
        WTF_CSRF_HEADERS=['X-CSRFToken'],
        WTF_CSRF_ENABLED=True
    )
    
    # Rate limiting is now configured in extensions.py with Redis

def configure_logging() -> None:
    """Configure application logging"""
    # Set log level based on environment variable or default to INFO
    log_level = os.getenv("LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

def init_app_components() -> None:
    """Initialize Flask extensions and components"""
    # Apply proxy fix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # Initialize extensions
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    
    csrf.init_app(app)
    limiter.init_app(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(chat_routes, url_prefix="/chat")
    app.register_blueprint(model_bp, url_prefix="/models")
    
    # Check if auth routes are properly registered
    if 'auth.register' not in app.view_functions:
        logger.error("Auth routes failed to register properly")
        raise RuntimeError("Auth routes failed to register properly")
    
    # Initialize database
    init_app(app)
    
    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# --- Error Handlers ---
@app.errorhandler(400)
def bad_request(error: HTTPException) -> Tuple[Dict[str, str], int]:
    """Handle HTTP 400 Bad Request errors"""
    logger.exception("400 Bad Request - URL: %s", request.url)
    return jsonify(
        error="Bad request",
        message=error.description or "Invalid request"
    ), 400

@app.errorhandler(403)
def forbidden(error: HTTPException) -> Tuple[Dict[str, str], int]:
    """Handle HTTP 403 Forbidden errors"""
    return jsonify(
        error="Forbidden",
        message="Access denied"
    ), 403

@app.errorhandler(404)
def not_found(error: HTTPException) -> Tuple[Dict[str, str], int]:
    """Handle HTTP 404 Not Found errors"""
    return jsonify(
        error="Not found",
        message="Resource not found"
    ), 404

@app.errorhandler(429)
def rate_limit_exceeded(error: HTTPException) -> Tuple[Dict[str, str], int]:
    """Handle HTTP 429 Too Many Requests errors"""
    return jsonify(
        error="Rate limit exceeded",
        message="Please try again later"
    ), 429

@app.errorhandler(500)
def internal_server_error(error: HTTPException) -> Tuple[Dict[str, str], int]:
    """Handle HTTP 500 Internal Server Error"""
    logger.error(f"500 Internal Server Error: {error} - URL: {request.url}")
    return jsonify(
        error="Internal server error",
        message="An unexpected error occurred"
    ), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all uncaught exceptions"""
    logger.exception("Unhandled exception occurred - URL: %s, Method: %s, User: %s, Error: %s",
                    request.url, request.method,
                    current_user.id if current_user.is_authenticated else 'anonymous',
                    str(e))
    return jsonify(
        error="An internal error occurred",
        message="Please try again later"
    ), 500

@app.before_request
def log_request_info():
    try:
        # Generate correlation ID
        g.correlation_id = str(uuid.uuid4())
        
        # Log basic request info without sensitive data
        logger.info("Request received - Method: %s, Path: %s, Remote IP: %s, Correlation ID: %s",
                   request.method, request.path, request.remote_addr, g.correlation_id)
    except Exception as e:
        logger.error("Error logging request: %s", str(e))
        
@app.errorhandler(CSRFError)
def handle_csrf_error(e: CSRFError) -> Tuple[Dict[str, str], int]:
    """Handle CSRF token errors"""
    return jsonify(
        error="Invalid CSRF token",
        message="Please refresh and try again"
    ), 400

# --- Routes ---
@app.route("/favicon.ico")
def favicon() -> Response:
    """Handle favicon requests"""
    return redirect(url_for("static", filename="favicon.ico"))

@app.route("/")
def index() -> Response:
    """Root URL handler"""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("chat.chat_interface"))

@app.route("/clear-session")
def clear_session() -> Response:
    """Clear user session"""
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))

# --- User Loader ---
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user by ID"""
    try:
        db = get_db()
        result = db.execute(
            text("SELECT id, username, email, role FROM users WHERE id = :id"),
            {"id": int(user_id)}
        ).fetchone()
        return User(**dict(zip(["id", "username", "email", "role"], result))) if result else None
    except Exception as e:
        app.logger.error(f"Error loading user: {e}")
        return None
    finally:
        db.close()

# --- Application Initialization ---
configure_logging()
configure_app()
configure_security()
init_app_components()

# --- Application Entry Point ---
if __name__ == "__main__":
    ssl_context = configure_ssl()
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        ssl_context=ssl_context,
        debug=False
    )
