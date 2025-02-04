"""Configuration module for the application."""

import os
import logging
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Model configuration
MODEL_CONFIG = {
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

# File type configurations
FILE_CONFIG = {
    "ALLOWED_EXTENSIONS": {"txt", "pdf", "md", "html", "docx", "pptx", "py"},
    "MIME_TYPES": {
        "pdf": "application/pdf",
        "txt": "text/plain",
        "html": "text/html",
        "md": "text/markdown",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "py": "text/x-python",
    },
}


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration values.
    """
    if not config["SECRET_KEY"] or len(config["SECRET_KEY"]) < 12:
        raise ValueError("SECRET_KEY must be at least 12 characters long")

    db_uri = config["DATABASE_URI"]
    parsed = urlparse(db_uri)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg2"}:
        raise ValueError(f"Invalid DATABASE_URI scheme: {parsed.scheme}")
    if not parsed.netloc or not parsed.path or parsed.path == "/":
        raise ValueError("Invalid DATABASE_URI: Missing host/port or database name")

    required_vars = {"ENCRYPTION_KEY", "AZURE_OPENAI_KEY", "AZURE_DEPLOYMENT_NAME"}
    missing = [var for var in required_vars if not config.get(var)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    if config["DEFAULT_MAX_TOKENS"] <= 0:
        raise ValueError("DEFAULT_MAX_TOKENS must be positive")
    if config["DEFAULT_MAX_COMPLETION_TOKENS"] <= 0:
        raise ValueError("DEFAULT_MAX_COMPLETION_TOKENS must be positive")

    if config["DEBUG"] and config["ENV"] == "production":
        raise ValueError("Debug mode cannot be enabled in production environment")


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class Config:
    """
    Application configuration.
    """

    MODEL_CAPABILITIES = MODEL_CONFIG  # Expose model config to other modules

    def __init__(self):
        # Load environment variables from .env file
        env_path = Path(os.path.dirname(os.path.abspath(__file__))) / ".env"
        if not env_path.exists():
            raise ValueError(
                "Missing .env file. Please create one using .env.template as a guide."
            )
        load_dotenv(dotenv_path=str(env_path), override=True)

        # Environment and debug settings
        self.ENV = os.getenv("FLASK_ENV", "production")
        self.DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
        self.LOG_LEVEL = "DEBUG" if self.DEBUG else os.getenv("LOG_LEVEL", "INFO")
        self.SUPPRESS_WERKZEUG_LOGS = True

        # Core settings
        self.SECRET_KEY = os.getenv("SECRET_KEY")
        self.DATABASE_URI = os.getenv("DATABASE_URI", "")
        if self.DATABASE_URI.startswith("postgres://"):
            self.DATABASE_URI = self.DATABASE_URI.replace(
                "postgres://", "postgresql://", 1
            )

        # Azure OpenAI settings
        self.AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
  # Match the env var name exactly
        self.AZURE_API_ENDPOINT = os.getenv(
            "AZURE_OPENAI_ENDPOINT", "https://hp-east2.openai.azure.com"
        )
        self.AZURE_API_VERSION = os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
        )
        self.AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

        # Model settings
        self.MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")
        self.DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "Default Model")
        self.DEFAULT_DEPLOYMENT_NAME = os.getenv(
            "DEFAULT_DEPLOYMENT_NAME", self.AZURE_DEPLOYMENT_NAME
        )
        self.DEFAULT_MODEL_DESCRIPTION = os.getenv(
            "DEFAULT_MODEL_DESCRIPTION", "Default model description"
        )
        self.DEFAULT_API_ENDPOINT = os.getenv(
            "DEFAULT_API_ENDPOINT", self.AZURE_API_ENDPOINT
        )
        self.DEFAULT_API_VERSION = os.getenv(
            "DEFAULT_API_VERSION", self.AZURE_API_VERSION
        )
        self.DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
        self.DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "16384"))
        self.DEFAULT_MAX_COMPLETION_TOKENS = int(
            os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "16384")
        )
        self.DEFAULT_REQUIRES_O1_HANDLING = bool(
            os.getenv("DEFAULT_REQUIRES_O1_HANDLING", False)
        )
        self.DEFAULT_SUPPORTS_STREAMING = bool(
            os.getenv("DEFAULT_SUPPORTS_STREAMING", True)
        )
        self.MAX_TOKENS = int(os.getenv("MAX_TOKENS", "16384"))
        self.MAX_MESSAGE_TOKENS = int(os.getenv("MAX_MESSAGE_TOKENS", "16384"))

        # File handling settings
        self.UPLOAD_FOLDER = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "uploads"
        )
        self.MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))
        self.MAX_TOTAL_FILE_SIZE = int(
            os.getenv("MAX_TOTAL_FILE_SIZE", 50 * 1024 * 1024)
        )
        self.ALLOWED_FILE_EXTENSIONS = FILE_CONFIG["ALLOWED_EXTENSIONS"]
        self.ALLOWED_MIME_TYPES = set(FILE_CONFIG["MIME_TYPES"].values())
        self.MIME_TYPE_MAP = FILE_CONFIG["MIME_TYPES"]

        # Security settings
        self.ENCRYPTION_KEY = self._process_encryption_key(
            os.getenv("ENCRYPTION_KEY", "")
        )
        self.PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))
        self.PASSWORD_REQUIRE_UPPERCASE = bool(
            os.getenv("PASSWORD_REQUIRE_UPPERCASE", True)
        )
        self.PASSWORD_REQUIRE_LOWERCASE = bool(
            os.getenv("PASSWORD_REQUIRE_LOWERCASE", True)
        )
        self.PASSWORD_REQUIRE_NUMBER = bool(os.getenv("PASSWORD_REQUIRE_NUMBER", True))
        self.PASSWORD_REQUIRE_SPECIAL_CHAR = bool(
            os.getenv("PASSWORD_REQUIRE_SPECIAL_CHAR", True)
        )

        # Session settings
        self.PERMANENT_SESSION_LIFETIME = int(
            os.getenv("PERMANENT_SESSION_LIFETIME", "3600")
        )
        self.SESSION_COOKIE_SECURE = bool(os.getenv("SESSION_COOKIE_SECURE", False))
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = "Lax"

        # Email settings
        self.EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@example.com")
        self.SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.example.com")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USERNAME = os.getenv("SMTP_USERNAME", "your-smtp-username")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your-smtp-password")

        # Application settings
        self.APP_URL = os.getenv("APP_URL", "http://localhost:5000")

        # Validate configuration
        validate_config(self.__dict__)

    def _process_encryption_key(self, key: str) -> str:
        """
        Process encryption key for use with Fernet.
        """
        if not key:
            raise ValueError("ENCRYPTION_KEY environment variable is required")
        key_bytes = hashlib.sha256(key.encode()).digest()
        return base64.b64encode(key_bytes).decode()
