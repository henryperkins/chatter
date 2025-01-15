import os
import logging
from concurrent_log_handler import ConcurrentRotatingFileHandler
from utils.config import Config
from .formatters import JsonFormatter, DETAILED_FORMAT, SIMPLE_FORMAT

# Log directory setup
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logger(name: str, log_file: str, level=logging.INFO, formatter=DETAILED_FORMAT) -> logging.Logger:
    """Setup a logger with a specific name, file, level, and formatter.
    
    Args:
        name: Logger name
        log_file: Path to log file
        level: Logging level
        formatter: Log format string
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Create a rotating file handler
    handler = ConcurrentRotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5  # 10 MB
    )
    handler.setFormatter(logging.Formatter(formatter))
    logger.addHandler(handler)

    # Prevent log propagation to the root logger
    logger.propagate = False
    return logger


def configure_logging():
    """Configure application-wide logging settings."""
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(Config.LOG_LEVEL)

    # Add a rotating file handler to the root logger
    root_handler = ConcurrentRotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"),
        maxBytes=20 * 1024 * 1024,  # 20 MB
        backupCount=10
    )
    root_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    root_logger.addHandler(root_handler)

    # Add a console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(SIMPLE_FORMAT))
    root_logger.addHandler(console_handler)

    # Use JSON logging in production
    if os.getenv("FLASK_ENV") == "production":
        json_formatter = JsonFormatter()
        root_handler.setFormatter(json_formatter)
        console_handler.setFormatter(json_formatter)

    # Configure third-party library loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # Application-specific loggers
    setup_logger("chat_api", os.path.join(LOG_DIR, "api.log"))
    setup_logger("httpx", os.path.join(LOG_DIR, "http.log"), level=logging.WARNING)
    setup_logger("user_actions", os.path.join(LOG_DIR, "user_actions.log"))
    setup_logger("errors", os.path.join(LOG_DIR, "errors.log"), level=logging.ERROR)


# Expose logconfig_dict for Gunicorn
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detailed": {
            "format": DETAILED_FORMAT,
        },
        "simple": {
            "format": SIMPLE_FORMAT,
        },
        "json": {
            "()": JsonFormatter,
        },
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "detailed",
            "filename": os.path.join(LOG_DIR, "gunicorn.log"),
            "maxBytes": 20 * 1024 * 1024,  # 20 MB
            "backupCount": 5,
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "detailed",
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["file", "console"],
    },
}