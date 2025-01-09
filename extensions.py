# extensions.py
import os
import logging

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

logger = logging.getLogger(__name__)

# Initialize Flask-Login
login_manager = LoginManager()

# Initialize CSRF Protection
csrf = CSRFProtect()

# Alias for csrf.protect
csrf_protect = csrf.protect

# Initialize Limiter
redis_url = os.getenv("REDIS_URL")

if redis_url:
    try:
        limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)
        logger.info("Flask-Limiter is configured to use Redis.")
    except Exception as e:
        logger.error(f"Failed to configure Redis for Flask-Limiter: {e}")
        raise RuntimeError("Redis configuration for Flask-Limiter failed.")
else:
    limiter = Limiter(key_func=get_remote_address)
    logger.warning("Using in-memory storage for Flask-Limiter. This is not recommended for production.")
