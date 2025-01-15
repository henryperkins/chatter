import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///./data/chat_app.db")
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "your-encryption-key")

    AZURE_API_KEY = os.getenv("AZURE_API_KEY", "your-azure-api-key")
    AZURE_API_ENDPOINT = os.getenv("AZURE_API_ENDPOINT", "https://openai.azure.com/")
    AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    AZURE_DEPLOYMENT_NAME = os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_NAME", "default-deployment"
    )

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

    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
    DEFAULT_MAX_TOKENS = None
    DEFAULT_MAX_COMPLETION_TOKENS = int(
        os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", 8300)
    )
    DEFAULT_REQUIRES_O1_HANDLING = bool(os.getenv("DEFAULT_REQUIRES_O1_HANDLING", True))
    DEFAULT_SUPPORTS_STREAMING = bool(os.getenv("DEFAULT_SUPPORTS_STREAMING", False))

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
