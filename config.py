import os
import logging
import re
from pathlib import Path
from typing import Dict, Set, Any
from urllib.parse import urlparse
from dotenv import load_dotenv

def validate_secret_key(key: str) -> None:
    """Validate that SECRET_KEY meets minimum security requirements."""
    if not key or len(key) < 12:
        raise ValueError("SECRET_KEY must be at least 12 characters long")

def validate_database_uri(uri: str) -> None:
    """Validate that DATABASE_URI is properly formatted."""
    try:
        parsed = urlparse(uri)

        # Check if the scheme is valid
        valid_schemes = {"postgresql", "postgres", "postgresql+psycopg2"}
        if parsed.scheme not in valid_schemes:
            raise ValueError(
                f"Invalid DATABASE_URI scheme: {parsed.scheme}. "
                f"Must be one of: {', '.join(valid_schemes)}"
            )

        # Check if the URI has a valid network location
        if not parsed.netloc:
            raise ValueError("Invalid DATABASE_URI: Missing host or port")

        # Check if the URI has a valid path (database name)
        if not parsed.path or parsed.path == "/":
            raise ValueError("Invalid DATABASE_URI: Missing database name")

    except Exception as e:
        raise ValueError(f"Invalid DATABASE_URI: {str(e)}")

# Load .env from current directory or parent directory
env_path = Path('.') / '.env'
if not env_path.exists():
    env_path = Path('..') / '.env'
load_dotenv(dotenv_path=env_path)


class Config:
    logger: logging.Logger = logging.getLogger(__name__)

    # Load environment variables
    ENV = os.getenv("FLASK_ENV", "production")

    # Required configuration
    REQUIRED_CONFIG: Set[str] = {
        "SECRET_KEY",
        "DATABASE_URI",
        "ENCRYPTION_KEY",
        "AZURE_API_KEY"
    }

    # Validate required configuration
    for var in REQUIRED_CONFIG:
        value = os.getenv(var)
        if not value:
            raise ValueError(f"{var} environment variable is not set")

        # Special validation for sensitive keys
        if var == "SECRET_KEY":
            validate_secret_key(value)
        elif var == "DATABASE_URI":
            validate_database_uri(value)

        # Set the attribute directly on the class
        globals()[var] = value

    # Add encryption key configuration
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    if not ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY environment variable is required")

    # Ensure encryption key is properly formatted for Fernet
    # Fernet requires a 32-byte key encoded in base64
    import base64
    try:
        # If the key is already base64, this will work
        base64.b64decode(ENCRYPTION_KEY, validate=True)
    except Exception:
        # If not, encode it as base64
        # First ensure it's 32 bytes by hashing if needed
        from cryptography.fernet import Fernet
        import hashlib
        key_bytes = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        ENCRYPTION_KEY = base64.b64encode(key_bytes).decode()
        logger.info("Encryption key properly formatted for Fernet usage")

    # Add explicit Azure configuration
    AZURE_API_KEY = os.getenv("AZURE_API_KEY")
    if not AZURE_API_KEY:
        raise ValueError("AZURE_API_KEY environment variable is required")
    AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-deployment")
    AZURE_API_ENDPOINT = os.getenv("AZURE_API_ENDPOINT", "https://hp-east2.openai.azure.com/openai/deployments")
    AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-deployment")

    # Added missing default model configurations
    DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "Default Model")
    DEFAULT_DEPLOYMENT_NAME = os.getenv(
        "DEFAULT_DEPLOYMENT_NAME", AZURE_DEPLOYMENT_NAME
    )
    DEFAULT_MODEL_DESCRIPTION = os.getenv(
        "DEFAULT_MODEL_DESCRIPTION", "Default model description"
    )
    DEFAULT_API_ENDPOINT = os.getenv("DEFAULT_API_ENDPOINT", AZURE_API_ENDPOINT)
    DEFAULT_TEMPERATURE: float = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
    try:
        DEFAULT_MAX_TOKENS: int = int(os.getenv("DEFAULT_MAX_TOKENS", "16384"))
        if DEFAULT_MAX_TOKENS <= 0:
            raise ValueError("DEFAULT_MAX_TOKENS must be positive")
    except ValueError as e:
        raise ValueError(f"Invalid DEFAULT_MAX_TOKENS value: {str(e)}")

    try:
        DEFAULT_MAX_COMPLETION_TOKENS: int = int(
            os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "16384")
        )
        if DEFAULT_MAX_COMPLETION_TOKENS <= 0:
            raise ValueError("DEFAULT_MAX_COMPLETION_TOKENS must be positive")
    except ValueError as e:
        raise ValueError(f"Invalid DEFAULT_MAX_COMPLETION_TOKENS value: {str(e)}")
    DEFAULT_REQUIRES_O1_HANDLING = bool(os.getenv("DEFAULT_REQUIRES_O1_HANDLING", True))
    DEFAULT_SUPPORTS_STREAMING = bool(os.getenv("DEFAULT_SUPPORTS_STREAMING", False))
    DEFAULT_API_VERSION = os.getenv("DEFAULT_API_VERSION", AZURE_API_VERSION)

    EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@example.com")
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.example.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "your-smtp-username")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your-smtp-password")

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))
    MAX_TOTAL_FILE_SIZE = int(os.getenv("MAX_TOTAL_FILE_SIZE", 50 * 1024 * 1024))
    ALLOWED_FILE_EXTENSIONS = {
        "txt",
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "csv",
        "py",
        "js",
        "md",
    }
    ALLOWED_MIME_TYPES = {
        'text/plain',
        'text/markdown',
        'text/x-python',
        'text/javascript',
        'text/css',
        'text/html',
        'text/csv',
        'application/json',
        'application/pdf',
        'application/javascript',
        'application/x-javascript',
        'application/octet-stream',  # Will be handled with special text detection
        'image/jpeg',
        'image/png',
        'image/gif'
    }

    MIME_TYPE_MAP = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "txt": "text/plain",
        "csv": "text/csv",
        "py": "text/x-python",
        "js": "application/javascript",
        "json": "application/json",
        "css": "text/css",
        "html": "text/html",
        "md": "text/markdown",
        "gif": "image/gif"
    }

    MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", 16384))
    MAX_MESSAGE_TOKENS = int(os.getenv("MAX_MESSAGE_TOKENS", 16384))

    PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", 8))
    PASSWORD_REQUIRE_UPPERCASE = bool(os.getenv("PASSWORD_REQUIRE_UPPERCASE", True))
    PASSWORD_REQUIRE_LOWERCASE = bool(os.getenv("PASSWORD_REQUIRE_LOWERCASE", True))
    PASSWORD_REQUIRE_NUMBER = bool(os.getenv("PASSWORD_REQUIRE_NUMBER", True))
    PASSWORD_REQUIRE_SPECIAL_CHAR = bool(
        os.getenv("PASSWORD_REQUIRE_SPECIAL_CHAR", True)
    )

    APP_URL = os.getenv("APP_URL", "http://localhost:5000")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Debug mode settings
    DEBUG: bool = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
    SUPPRESS_WERKZEUG_LOGS = True  # Set to False to see Werkzeug's internal logs
    if DEBUG:
        if os.getenv("FLASK_ENV") == "production":
            raise ValueError("Debug mode cannot be enabled in production environment")
        LOG_LEVEL = "DEBUG"  # Automatically set more verbose logging in debug mode
        logger.warning("Debug mode is enabled - not recommended for production")

    PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", 3600))
    SESSION_COOKIE_SECURE = bool(os.getenv("SESSION_COOKIE_SECURE", False))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
