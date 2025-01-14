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

# Initialize Limiter with memory storage by default
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200 per day", "50 per hour"],
    strategy="fixed-window",
)

# Only try Redis if explicitly configured
if os.getenv("USE_REDIS_LIMITER") and os.getenv("REDIS_URL"):
    try:
        redis_url = os.getenv("REDIS_URL")
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=redis_url,
            default_limits=["200 per day", "50 per hour"],
            strategy="fixed-window",
        )
        logger.info("Flask-Limiter configured with Redis")
    except Exception as e:
        logger.warning(f"Redis configuration failed, using memory storage: {e}")
