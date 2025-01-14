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
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

try:
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=redis_url,
        default_limits=["200 per day", "50 per hour"]
    )
    logger.info("Flask-Limiter is configured to use Redis.")
except Exception as e:
    logger.error(f"Failed to configure Redis for Flask-Limiter: {e}")
    raise RuntimeError("Redis configuration for Flask-Limiter failed.")
