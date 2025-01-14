"""
Authentication utility functions.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from contextlib import contextmanager

from flask import request
from flask_limiter.util import get_remote_address

from database import get_db

logger = logging.getLogger(__name__)

# Track failed attempts
failed_logins: Dict[str, List[datetime]] = {}
failed_registrations: Dict[str, List[datetime]] = {}

@contextmanager
def db_session():
    """Database session context manager."""
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def clean_failed_attempts(attempts_dict: Dict[str, List[datetime]], minutes: int = 15) -> None:
    """Clean up old failed attempts from tracking dictionary."""
    now = datetime.now()
    to_delete = []
    for key, timestamps in attempts_dict.items():
        attempts_dict[key] = [
            ts for ts in timestamps if now - ts < timedelta(minutes=minutes)
        ]
        if not attempts_dict[key]:
            to_delete.append(key)
    for key in to_delete:
        del attempts_dict[key]

def check_attempts(identifier: str, attempts_dict: Dict[str, List[datetime]], max_attempts: int = 5) -> bool:
    """Check if the identifier has exceeded allowed attempts."""
    now = datetime.now()
    attempts = attempts_dict.get(identifier, [])
    attempts = [t for t in attempts if now - t < timedelta(minutes=15)]
    attempts_dict[identifier] = attempts
    return len(attempts) < max_attempts

def limiter_key():
    """Rate limit key based on IP and username."""
    username = request.form.get("username", "")
    return f"{get_remote_address()}:{username}"

def log_failed_attempt(identifier: str, attempts_dict: Dict[str, List[datetime]]) -> None:
    """Log a failed attempt for the given identifier."""
    attempts_dict.setdefault(identifier, []).append(datetime.now())
    clean_failed_attempts(attempts_dict)