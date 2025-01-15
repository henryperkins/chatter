import os

class Config:
    """Centralized configuration class for the application."""

    # General Configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")  # Flask secret key
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///chat_app.db")  # Database URI
    ENCRYPTION_KEY = os.getenv(
        "ENCRYPTION_KEY", "your-encryption-key"
    )  # Encryption key

    # Azure OpenAI Configuration
    AZURE_API_KEY = os.getenv("AZURE_API_KEY", "your-azure-api-key")  # Azure API key
    AZURE_API_ENDPOINT = os.getenv(
        "AZURE_API_ENDPOINT", "https://openai.azure.com/"
    )  # Azure API endpoint
    AZURE_API_VERSION = os.getenv(
        "AZURE_API_VERSION", "2024-12-01-preview"
    )  # Azure API version
    AZURE_DEPLOYMENT_NAME = os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_NAME", "default-deployment"
    )  # Azure deployment name

    # Email Configuration
    EMAIL_SENDER = os.getenv(
        "EMAIL_SENDER", "no-reply@example.com"
    )  # Default sender email
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.example.com")  # SMTP server
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))  # SMTP port
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "your-smtp-username")  # SMTP username
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your-smtp-password")  # SMTP password

    # File Upload Configuration
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")  # File upload directory
    MAX_FILE_SIZE = int(
        os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024)
    )  # Max file size (10 MB)
    MAX_TOTAL_FILE_SIZE = int(
        os.getenv("MAX_TOTAL_FILE_SIZE", 50 * 1024 * 1024)
    )  # Max total size for all files (50 MB)
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
    }  # Allowed file extensions
    MIME_TYPE_MAP = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "txt": "text/plain",
        "csv": "text/csv",
        "py": "text/x-python",
        "js": "application/javascript",
        "md": "text/markdown",
    }  # MIME type mappings for file validation

    # Token Configuration
    MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")  # Default model name
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", 32000))  # Max tokens per request
    MAX_MESSAGE_TOKENS = int(
        os.getenv("MAX_MESSAGE_TOKENS", 32000)
    )  # Max tokens per message

    # Default Model Configuration for Azure OpenAI
    DEFAULT_TEMPERATURE = float(
        os.getenv("DEFAULT_TEMPERATURE", "1.0")
    )  # Default temperature (o1-preview requires exactly 1.0)
    DEFAULT_MAX_TOKENS = None  # o1-preview doesn't use max_tokens
    DEFAULT_MAX_COMPLETION_TOKENS = int(
        os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", 8300)
    )  # Max completion tokens for o1-preview
    DEFAULT_REQUIRES_O1_HANDLING = bool(
        os.getenv("DEFAULT_REQUIRES_O1_HANDLING", True)
    )  # Enable o1-preview specific handling
    DEFAULT_SUPPORTS_STREAMING = bool(
        os.getenv("DEFAULT_SUPPORTS_STREAMING", False)
    )  # o1-preview doesn't support streaming

    # Default model configuration dictionary
    DEFAULT_MODEL_CONFIG = {
        "name": MODEL_NAME,
        "deployment_name": AZURE_DEPLOYMENT_NAME,
        "api_endpoint": AZURE_API_ENDPOINT,
        "api_key": AZURE_API_KEY,
        "api_version": AZURE_API_VERSION,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "max_completion_tokens": DEFAULT_MAX_COMPLETION_TOKENS,
        "requires_o1_handling": DEFAULT_REQUIRES_O1_HANDLING,
        "supports_streaming": DEFAULT_SUPPORTS_STREAMING,
    }

    # Password Policy Configuration
    PASSWORD_MIN_LENGTH = int(
        os.getenv("PASSWORD_MIN_LENGTH", 8)
    )  # Min password length
    PASSWORD_REQUIRE_UPPERCASE = bool(
        os.getenv("PASSWORD_REQUIRE_UPPERCASE", True)
    )  # Require uppercase letters
    PASSWORD_REQUIRE_LOWERCASE = bool(
        os.getenv("PASSWORD_REQUIRE_LOWERCASE", True)
    )  # Require lowercase letters
    PASSWORD_REQUIRE_NUMBER = bool(
        os.getenv("PASSWORD_REQUIRE_NUMBER", True)
    )  # Require numbers
    PASSWORD_REQUIRE_SPECIAL_CHAR = bool(
        os.getenv("PASSWORD_REQUIRE_SPECIAL_CHAR", True)
    )  # Require special characters

    # Application URL (for email links)
    APP_URL = os.getenv("APP_URL", "http://localhost:5000")  # Default application URL

    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # Default log level

    # Session Configuration
    PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", 3600))  # Default: 1 hour
    SESSION_COOKIE_SECURE = bool(os.getenv("SESSION_COOKIE_SECURE", False))  # Secure cookies (HTTPS only)
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to cookies
    SESSION_COOKIE_SAMESITE = "Lax"  # Restrict cross-site cookie sharing