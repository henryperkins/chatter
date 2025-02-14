"""Configuration module for the application."""

import os
import logging
import base64
from cryptography.fernet import Fernet
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Model configuration
MODEL_CONFIG = {
    "o1": {
        "required_params": [
            "deployment_name",
            "api_version",
            "max_completion_tokens",
            "reasoning_effort"
        ],
        "fixed_params": {
            "temperature": 1.0,
            "top_p": 1.0,
            "supports_streaming": False
        },
        "capabilities": {
            "max_tokens": 200000,
            "max_completion_tokens": 100000,
            "supports_function_calling": True,
            "supports_vision": True,
            "requires_reasoning_effort": True,
            "valid_reasoning_efforts": ["low", "medium", "high"]
        }
    },
    "o1-mini": {
        "required_params": [
            "deployment_name",
            "api_version",
            "max_completion_tokens",
            "reasoning_effort"
        ],
        "fixed_params": {
            "temperature": 1.0,
            "top_p": 1.0,
            "supports_streaming": False
        },
        "capabilities": {
            "max_tokens": 100000,
            "max_completion_tokens": 50000,
            "supports_function_calling": True,
            "supports_vision": False,
            "requires_reasoning_effort": True,
            "valid_reasoning_efforts": ["low", "medium", "high"]
        }
    },
    "o1-preview": {
        "required_params": [
            "deployment_name",
            "api_version",
            "max_completion_tokens",
            "reasoning_effort"
        ],
        "fixed_params": {
            "temperature": 1.0,
            "top_p": 1.0,
            "supports_streaming": False
        },
        "capabilities": {
            "max_tokens": 200000,
            "max_completion_tokens": 100000,
            "supports_function_calling": True,
            "supports_vision": True,
            "requires_reasoning_effort": True,
            "valid_reasoning_efforts": ["low", "medium", "high"]
        }
    },
    "o3-mini": {
        "required_params": [
            "deployment_name",
            "api_version",
            "max_completion_tokens",
            "reasoning_effort"
        ],
        "fixed_params": {
            "temperature": 1.0,
            "top_p": 1.0,
            "supports_streaming": False
        },
        "capabilities": {
            "max_tokens": 150000,
            "max_completion_tokens": 75000,
            "supports_function_calling": True,
            "supports_vision": False,
            "requires_reasoning_effort": True,
            "valid_reasoning_efforts": ["low", "medium", "high"]
        }
    },
    "azure": {
        "supports_streaming": True,
        "max_tokens": 16384,
        "token_overhead": 3,
        "endpoint_format": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
        "api_version": "2024-12-01-preview",
    }
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

def validate_model_config(config: dict) -> None:
    """Validate model configuration based on model type."""
    model_type = config.get("model_type")
    if model_type == "o1-preview":
        if config.get("temperature") != 1.0:
            raise ValueError("o1-preview models require temperature=1.0")
        if config.get("max_completion_tokens", 0) > 100000:
            raise ValueError("max_completion_tokens exceeds 100k limit for o1-preview")
        if config.get("reasoning_effort") not in ["low", "medium", "high"]:
            raise ValueError("Invalid reasoning_effort value for o1-preview")

def validate_config(config: Dict[str, Any]) -> None:
    """Validate configuration values."""
    if not config["SECRET_KEY"] or len(config["SECRET_KEY"]) < 12:
        raise ValueError("SECRET_KEY must be at least 12 characters long")

    db_uri = config["DATABASE_URI"]
    parsed = urlparse(db_uri)
    allowed_schemes = {"postgresql", "postgresql+psycopg2", "postgres"}
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"Invalid DATABASE_URI scheme: {parsed.scheme}. " 
                         "Allowed schemes: postgresql, postgresql+psycopg2, postgres")
    if not parsed.netloc or not parsed.path or parsed.path == "/":
        raise ValueError("Invalid DATABASE_URI: Missing host/port or database name")

    required_vars = {"ENCRYPTION_KEY", "AZURE_OPENAI_KEY"}
    missing = [var for var in required_vars if not config.get(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

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
    """Application configuration."""
    _instance = None
    MODEL_CAPABILITIES = MODEL_CONFIG

    @classmethod
    def log_env_values(cls):
        """Log non-sensitive environment values."""
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()
        logger.info("Azure OpenAI endpoint: %s", azure_endpoint)
        logger.info("Azure OpenAI API version: %s", api_version)
        logger.info("Azure OpenAI deployment: %s", deployment)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Load environment variables
        env_path = Path(os.path.dirname(os.path.abspath(__file__))) / ".env"
        if not env_path.exists():
            raise ValueError("Missing .env file. Please create one using .env.template as a guide.")
        load_dotenv(dotenv_path=str(env_path), override=True)

        # Environment and debug settings
        self.ENV = os.getenv("FLASK_ENV", "production")
        self.DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
        self.LOG_LEVEL = "DEBUG" if self.DEBUG else os.getenv("LOG_LEVEL", "INFO")
        self.SUPPRESS_WERKZEUG_LOGS = True
        # Force SESSION_COOKIE_SECURE = False in development to avoid cookie issues on HTTP
        if self.ENV.lower() == "development":
            os.environ["SESSION_COOKIE_SECURE"] = "False"

        # Core settings
        self.SECRET_KEY = os.getenv("SECRET_KEY")
        self.DATABASE_URI = os.getenv("DATABASE_URI", "")
        
        # Convert postgres:// to postgresql:// if needed
        parsed = urlparse(self.DATABASE_URI)
        if parsed.scheme == 'postgres':
            # Automatically convert postgres:// to postgresql://
            parsed = parsed._replace(scheme='postgresql')
            self.DATABASE_URI = urlunparse(parsed)
            logger.info(f"Converted database URI from postgres:// to postgresql://: {self.DATABASE_URI}")

        # Azure OpenAI settings
        self.AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
        self.AZURE_API_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://o1models.openai.azure.com").strip()
        self.AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
        self.AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "o1-east2")

        # Model settings
        self.MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "Azure o1")
        self.DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "Azure o1")
        self.DEFAULT_DEPLOYMENT_NAME = os.getenv("DEFAULT_DEPLOYMENT_NAME", self.AZURE_DEPLOYMENT_NAME)
        self.DEFAULT_MODEL_TYPE = os.getenv("DEFAULT_MODEL_TYPE", "o1-preview")
        self.DEFAULT_API_ENDPOINT = os.getenv("DEFAULT_API_ENDPOINT", self.AZURE_API_ENDPOINT)
        self.DEFAULT_API_VERSION = os.getenv("DEFAULT_API_VERSION", self.AZURE_API_VERSION)
        self.DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
        self.DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "200000"))
        self.DEFAULT_MAX_COMPLETION_TOKENS = int(os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "100000"))
        self.DEFAULT_REASONING_EFFORT = os.getenv("DEFAULT_REASONING_EFFORT", "medium")
        self.DEFAULT_REQUIRES_O1_HANDLING = True
        self.DEFAULT_SUPPORTS_STREAMING = False

        # File handling settings
        self.UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
        self.MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))
        self.MAX_TOTAL_FILE_SIZE = int(os.getenv("MAX_TOTAL_FILE_SIZE", 50 * 1024 * 1024))
        self.ALLOWED_FILE_EXTENSIONS = FILE_CONFIG["ALLOWED_EXTENSIONS"]
        self.ALLOWED_MIME_TYPES: set[str] = {v for v in FILE_CONFIG["MIME_TYPES"].values()}
        self.MIME_TYPE_MAP = FILE_CONFIG["MIME_TYPES"]

        # Security settings
        self.ENCRYPTION_KEY = self._process_encryption_key(os.getenv("ENCRYPTION_KEY", ""))
        self.PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))
        self.PASSWORD_REQUIRE_UPPERCASE = bool(os.getenv("PASSWORD_REQUIRE_UPPERCASE", True))
        self.PASSWORD_REQUIRE_LOWERCASE = bool(os.getenv("PASSWORD_REQUIRE_LOWERCASE", True))
        self.PASSWORD_REQUIRE_NUMBER = bool(os.getenv("PASSWORD_REQUIRE_NUMBER", True))
        self.PASSWORD_REQUIRE_SPECIAL_CHAR = bool(os.getenv("PASSWORD_REQUIRE_SPECIAL_CHAR", True))

        # Session settings
        self.PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", "3600"))
        self.SESSION_COOKIE_SECURE = True  # Always use secure cookies
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = "Lax"  # Required for cross-origin safety
        self.PREFERRED_URL_SCHEME = "https"  # Force HTTPS as preferred scheme

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

        # Log environment values only during first initialization
        if not hasattr(Config, '_logged'):
            self.log_env_values()
            Config._logged = True

    def _process_encryption_key(self, key: str) -> str:
        """Process encryption key for use with Fernet."""
        logger.debug("Processing encryption key (redacted) length=%d", len(key) if key else 0)

        if not key:
            raise ValueError("ENCRYPTION_KEY is missing. Check your .env setup.")
            
        key = key.strip()  # Remove any whitespace
        
        try:
            # First try to use the key directly with Fernet to validate it
            Fernet(key.encode())
            logger.debug("Using valid Fernet key")
            return key
        except Exception:
            # If that fails, try to process it into a valid Fernet key
            try:
                # Generate a 32-byte key using SHA256
                key_bytes = base64.urlsafe_b64decode(key.encode())
                if len(key_bytes) != 32:
                    key_bytes = key_bytes[:32].ljust(32, b'\0')  # Ensure exactly 32 bytes
                # Convert to Fernet key format (URL-safe base64)
                fernet_key = base64.urlsafe_b64encode(key_bytes)
                logger.debug("Successfully processed encryption key")
                return fernet_key.decode()
            except Exception as e:
                raise ValueError(f"Invalid encryption key format: {str(e)}")

    @staticmethod
    def validate_model_config(config: dict) -> None:
        """Validate model configuration."""
        validate_model_config(config)


# Finally, create a single global instance you can import in other modules.
config_instance = Config()
