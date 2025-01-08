import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Log directory and file setup
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE = os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y-%m-%d')}.log")

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5),  # 10 MB per file, keep 5 backups
        logging.StreamHandler(),  # Log to console
    ],
)

# Custom logger for user actions
user_logger = logging.getLogger("user_actions")
user_logger.setLevel(logging.INFO)
user_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, f"user_actions_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
user_logger.addHandler(user_handler)

# Custom logger for errors
error_logger = logging.getLogger("errors")
error_logger.setLevel(logging.ERROR)
error_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, f"errors_{datetime.now().strftime('%Y-%m-%d')}.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
error_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
error_logger.addHandler(error_handler)

# Example usage:
# logging.info("This is an info message.")
# user_logger.info("User logged in: user123")
# error_logger.error("An error occurred: ...")