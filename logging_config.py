import logging
import os
import json
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

# Logging format configurations
DETAILED_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d:%(funcName)s] - %(message)s"
SIMPLE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
USER_FORMAT = "%(asctime)s - %(message)s"


# JSON logging configuration
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record),
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
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_trace"] = self.formatStack(record.stack_info)

        # Add request context if available
        try:
            from flask import request

            if request:
                log_record.update(
                    {
                        "request_id": request.headers.get("X-Request-ID"),
                        "url": request.url,
                        "method": request.method,
                        "remote_addr": request.remote_addr,
                        "user_agent": request.headers.get("User-Agent"),
                        "referrer": request.referrer,
                        "user_id": getattr(request, "user_id", None),
                        "content_length": request.content_length,
                        "content_type": request.content_type,
                    }
                )
        except Exception:
            pass

        # Add correlation ID if available
        try:
            from flask import g

            if hasattr(g, "correlation_id"):
                log_record["correlation_id"] = g.correlation_id
            if hasattr(g, "user_id"):
                log_record["user_id"] = g.user_id
        except Exception:
            pass

        # Redact sensitive information
        if "api_key" in log_record.get("message", ""):
            log_record["message"] = log_record["message"].replace(
                log_record["message"].split("api_key=")[1].split("&")[0],
                "***REDACTED***",
            )

        return json.dumps(log_record)


# Filter class for HTTP client logs
class HttpClientFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING


# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)  # Capture INFO and above logs

# Add console handler for development environment
if os.getenv("FLASK_ENV") == "development":
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    root_logger.addHandler(console_handler)


# Ensure all loggers have handlers
def ensure_logger_handlers(logger_name, handler, formatter):
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False


# Application log handler
app_log_handler = ConcurrentRotatingFileHandler(
    filename=os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=20 * 1024 * 1024,  # 20 MB
    backupCount=10,
)
app_log_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
root_logger.addHandler(app_log_handler)

# Configure JSON logging for production after handler is created
if os.getenv("FLASK_ENV") == "production":
    json_formatter = JsonFormatter()
    app_log_handler.setFormatter(json_formatter)

# Configure third-party library logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# API logger configuration
api_logger = logging.getLogger("chat_api")
api_logger.setLevel(logging.INFO)
api_logger.propagate = False
api_handler = RotatingFileHandler(
    os.path.join(API_LOG_DIR, f"api_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
api_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
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
http_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
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
httpcore_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
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
error_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
error_logger.addHandler(error_handler)

# OpenAI client logger
openai_logger = logging.getLogger("openai")
openai_logger.setLevel(logging.WARNING)
openai_handler = RotatingFileHandler(
    os.path.join(API_LOG_DIR, f"openai_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
openai_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
openai_logger.addHandler(openai_handler)


def get_logger(name):
    """Helper function to get a logger with the proper configuration."""
    return logging.getLogger(name)
