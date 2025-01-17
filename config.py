import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is not set.")

    DATABASE_URI = os.getenv("DATABASE_URI")
    if not DATABASE_URI:
        raise ValueError("DATABASE_URI environment variable is not set.")

    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    if not ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY environment variable is not set.")

    AZURE_API_KEY = os.getenv("AZURE_API_KEY")
    if not AZURE_API_KEY:
        raise ValueError("AZURE_API_KEY environment variable is not set.")
    AZURE_API_ENDPOINT = os.getenv("AZURE_API_ENDPOINT", "https://openai.azure.com/")
    AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "o1-preview")

    # Added missing default model configurations
    DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "Default Model")
    DEFAULT_DEPLOYMENT_NAME = os.getenv(
        "DEFAULT_DEPLOYMENT_NAME", AZURE_DEPLOYMENT_NAME
    )
    DEFAULT_MODEL_DESCRIPTION = os.getenv(
        "DEFAULT_MODEL_DESCRIPTION", "Default model description"
    )
    DEFAULT_API_ENDPOINT = os.getenv("DEFAULT_API_ENDPOINT", AZURE_API_ENDPOINT)
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
    DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", 32000))
    DEFAULT_MAX_COMPLETION_TOKENS = int(
        os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", 8300)
    )
    DEFAULT_REQUIRES_O1_HANDLING = bool(os.getenv("DEFAULT_REQUIRES_O1_HANDLING", True))
    DEFAULT_SUPPORTS_STREAMING = bool(os.getenv("DEFAULT_SUPPORTS_STREAMING", False))
    DEFAULT_API_VERSION = os.getenv("DEFAULT_API_VERSION", AZURE_API_VERSION)

    EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@example.com")
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.example.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "your-smtp-username")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your-smtp-password")

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
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
    }

    MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", 32000))
    MAX_MESSAGE_TOKENS = int(os.getenv("MAX_MESSAGE_TOKENS", 32000))

    PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", 8))
    PASSWORD_REQUIRE_UPPERCASE = bool(os.getenv("PASSWORD_REQUIRE_UPPERCASE", True))
    PASSWORD_REQUIRE_LOWERCASE = bool(os.getenv("PASSWORD_REQUIRE_LOWERCASE", True))
    PASSWORD_REQUIRE_NUMBER = bool(os.getenv("PASSWORD_REQUIRE_NUMBER", True))
    PASSWORD_REQUIRE_SPECIAL_CHAR = bool(
        os.getenv("PASSWORD_REQUIRE_SPECIAL_CHAR", True)
    )

    APP_URL = os.getenv("APP_URL", "http://localhost:5000")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", 3600))
    SESSION_COOKIE_SECURE = bool(os.getenv("SESSION_COOKIE_SECURE", False))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
