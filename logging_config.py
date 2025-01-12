import logging
import os
from logging.handlers import RotatingFileHandler
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
DETAILED_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
SIMPLE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
USER_FORMAT = "%(asctime)s - %(message)s"

# Filter class for HTTP client logs
class HttpClientFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING

# Base configuration
logging.basicConfig(
    level=logging.INFO,
    format=DETAILED_FORMAT,
    handlers=[
        RotatingFileHandler(
            os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y-%m-%d')}.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)

# API logger configuration
api_logger = logging.getLogger("chat_api")
api_logger.setLevel(logging.INFO)
api_handler = RotatingFileHandler(
    os.path.join(API_LOG_DIR, f"api_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)
api_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
api_logger.addHandler(api_handler)

# HTTP client logger configuration
http_logger = logging.getLogger("httpx")
http_logger.setLevel(logging.WARNING)  # Only log warnings and errors
http_handler = RotatingFileHandler(
    os.path.join(HTTP_LOG_DIR, f"http_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5
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
    backupCount=5
)
httpcore_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
httpcore_handler.addFilter(HttpClientFilter())
httpcore_logger.addHandler(httpcore_handler)

# User actions logger
user_logger = logging.getLogger("user_actions")
user_logger.setLevel(logging.INFO)
user_handler = RotatingFileHandler(
    os.path.join(USER_LOG_DIR, f"user_actions_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)
user_handler.setFormatter(logging.Formatter(USER_FORMAT))
user_logger.addHandler(user_handler)

# Error logger
error_logger = logging.getLogger("errors")
error_logger.setLevel(logging.ERROR)
error_handler = RotatingFileHandler(
    os.path.join(ERROR_LOG_DIR, f"errors_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)
error_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
error_logger.addHandler(error_handler)

# OpenAI client logger
openai_logger = logging.getLogger("openai")
openai_logger.setLevel(logging.WARNING)
openai_handler = RotatingFileHandler(
    os.path.join(API_LOG_DIR, f"openai_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)
openai_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
openai_logger.addHandler(openai_handler)

def get_logger(name):
    """Helper function to get a logger with the proper configuration."""
    return logging.getLogger(name)