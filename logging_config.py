import logging
import os
import json
import platform
from logging.handlers import RotatingFileHandler
from concurrent_log_handler import ConcurrentRotatingFileHandler
from datetime import datetime

# Log directory and file setup
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Create subdirectories for different log types
API_LOG_DIR = os.path.join(LOG_DIR, "api")
HTTP_LOG_DIR = os.path.join(LOG_DIR, "http")
USER_LOG_DIR = os.path.join(LOG_DIR, "user")
ERROR_LOG_DIR = os.path.join(LOG_DIR, "error")

for directory in [API_LOG_DIR, HTTP_LOG_DIR, USER_LOG_DIR, ERROR_LOG_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Standardized logging format configurations
STANDARD_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s"
USER_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s"
JSON_FORMAT = {
    "timestamp": "%(asctime)s",
    "level": "%(levelname)s",
    "logger": "%(name)s",
    "file": "%(filename)s",
    "line": "%(lineno)d",
    "message": "%(message)s",
    "request_id": "%(request_id)s",
    "user_id": "%(user_id)s",
    "duration": "%(duration_ms)s"
}


# Enhanced JSON logging configuration
class SafeFormatter(logging.Formatter):
    def format(self, record):
        # Add default values for missing keys
        for key in ['user_id', 'request_id']:
            if not hasattr(record, key):
                setattr(record, key, 'none')
        return super().format(record)

class JsonFormatter(SafeFormatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "logger": record.name,
            "level": record.levelname,
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
            "message": record.getMessage(),
            "thread": record.threadName,
            "process": record.processName,
            "environment": os.getenv("FLASK_ENV", "development"),
            "application": "chat_app",
            "pid": os.getpid(),
            "host": platform.node(),
        }

        # Add request_id if available
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_trace"] = self.formatStack(record.stack_info)

        return json.dumps(log_record)


# Filter class for HTTP client logs
class HttpClientFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING


def configure_logging():
    # Clear existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure root logger with consistent levels
    root_logger.setLevel(logging.INFO)  # Capture INFO and above logs

    # Prevent propagation to ancestor loggers
    root_logger.propagate = False

    # Disable framework log propagation
    logging.getLogger("werkzeug").propagate = False
    logging.getLogger("flask").propagate = False

    # Set consistent logging levels across all loggers
    LOGGING_LEVELS = {
        "": logging.INFO,  # Root logger
        "sqlalchemy.engine": logging.WARNING,
        "werkzeug": logging.WARNING,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "openai": logging.WARNING,
        "chat_api": logging.INFO,
        "user_actions": logging.INFO,
        "errors": logging.ERROR,
        "token_usage": logging.DEBUG,
        "database": logging.INFO
    }

    for logger_name, level in LOGGING_LEVELS.items():
        logging.getLogger(logger_name).setLevel(level)

if not logging.getLogger().handlers:
    configure_logging()

# Add console handler for development environment
def configure_console_logging():
    if os.getenv("FLASK_ENV") == "development":
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))
        root_logger = logging.getLogger()
        root_logger.addHandler(console_handler)

configure_console_logging()


# Ensure all loggers have handlers
def ensure_logger_handlers(logger_name, handler, formatter):
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False


# Application log handler with structured logging
app_log_handler = ConcurrentRotatingFileHandler(
    filename=os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=20 * 1024 * 1024,  # 20 MB
    backupCount=10,
    encoding="utf-8",
    delay=False
)

# Use JSON formatter in production, standard in development
if os.getenv("FLASK_ENV") == "production":
    app_log_handler.setFormatter(JsonFormatter())
else:
    app_log_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))

# Add handler to root logger
def configure_app_logging():
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.addHandler(app_log_handler)

configure_app_logging()

# Configure JSON logging for production after handler is created
if os.getenv("FLASK_ENV") == "production":
    json_formatter = JsonFormatter()
    app_log_handler.setFormatter(json_formatter)

# Configure third-party library logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# Token usage logger configuration
token_logger = logging.getLogger("token_usage")
token_logger.setLevel(logging.DEBUG)  # Set to DEBUG to capture all token-related logs
token_logger.propagate = False
token_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, f"token_usage_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
token_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))
token_logger.addHandler(token_handler)

# API logger configuration
api_logger = logging.getLogger("chat_api")
api_logger.setLevel(logging.INFO)
api_logger.propagate = False
api_handler = RotatingFileHandler(
    os.path.join(API_LOG_DIR, f"api_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
api_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))
api_logger.addHandler(api_handler)

# HTTP client logger configuration
http_logger = logging.getLogger("httpx")
http_logger.setLevel(logging.WARNING)
http_logger.propagate = False
http_handler = RotatingFileHandler(
    os.path.join(HTTP_LOG_DIR, f"http_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
http_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))
http_handler.addFilter(HttpClientFilter())
http_logger.addHandler(http_handler)

# Configure httpcore logger similarly
httpcore_logger = logging.getLogger("httpcore")
httpcore_logger.setLevel(logging.WARNING)
httpcore_handler = RotatingFileHandler(
    os.path.join(HTTP_LOG_DIR, f"httpcore_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
httpcore_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))
httpcore_handler.addFilter(HttpClientFilter())
httpcore_logger.addHandler(httpcore_handler)

# User actions logger
user_logger = logging.getLogger("user_actions")
user_logger.setLevel(logging.INFO)
user_handler = RotatingFileHandler(
    os.path.join(
        USER_LOG_DIR, f"user_actions_{datetime.now().strftime('%Y-%m-%d')}.log"
    ),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
user_handler.setFormatter(logging.Formatter(USER_FORMAT))
user_logger.addHandler(user_handler)

# Error logger
error_logger = logging.getLogger("errors")
error_logger.setLevel(logging.ERROR)
error_handler = RotatingFileHandler(
    os.path.join(ERROR_LOG_DIR, f"errors_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
error_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))
error_logger.addHandler(error_handler)

# OpenAI client logger
openai_logger = logging.getLogger("openai")
openai_logger.setLevel(logging.WARNING)
openai_handler = RotatingFileHandler(
    os.path.join(API_LOG_DIR, f"openai_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
openai_handler.setFormatter(logging.Formatter(STANDARD_FORMAT))
openai_logger.addHandler(openai_handler)


def get_logger(name):
    """Helper function to get a logger with the proper configuration."""
    return logging.getLogger(name)
