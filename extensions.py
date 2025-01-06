# extensions.py
import os
import logging

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from limits.storage.redis import RedisStorage

# Initialize the Limiter with no app attached
limiter = Limiter(key_func=get_remote_address)

# Initialize Flask-Login
login_manager = LoginManager()

# Initialize CSRF Protection
csrf = CSRFProtect()

# Initialize Redis storage for rate limiting (optional)
redis_url = os.getenv("REDIS_URL")
if redis_url:
    try:
        storage = RedisStorage(redis_url)
        limiter.storage = storage
        logger.info("Flask-Limiter is configured to use Redis.")
    except Exception as e:
        logger.error(f"Failed to configure Redis for Flask-Limiter: {e}")
        raise RuntimeError("Redis configuration for Flask-Limiter failed.")
else:
    logger.warning(
        "Using in-memory storage for Flask-Limiter. This is not recommended for production."
    )
