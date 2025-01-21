"""
Authentication utility functions.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List

from flask import request
from flask_limiter.util import get_remote_address

# Initialize logger
logger = logging.getLogger(__name__)

# Track failed attempts
failed_logins: Dict[str, List[datetime]] = {}
failed_registrations: Dict[str, List[datetime]] = {}

def clean_failed_attempts(
    attempts_dict: Dict[str, List[datetime]], minutes: int = 15
) -> None:
    """
    Clean up old failed attempts from tracking dictionary.

    Args:
        attempts_dict: Dictionary tracking failed attempts.
        minutes: Time window in minutes to retain failed attempts.
    """
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
    logger.debug(
        "Cleaned up failed attempts", extra={"remaining_attempts": len(attempts_dict)}
    )

def check_attempts(
    identifier: str, attempts_dict: Dict[str, List[datetime]], max_attempts: int = 5
) -> bool:
    """
    Check if the identifier has exceeded allowed attempts.

    Args:
        identifier: The unique identifier (e.g., username or IP address).
        attempts_dict: Dictionary tracking failed attempts.
        max_attempts: Maximum allowed attempts.

    Returns:
        bool: True if attempts are within the limit, False otherwise.
    """
    now = datetime.now()
    attempts = attempts_dict.get(identifier, [])
    attempts = [t for t in attempts if now - t < timedelta(minutes=15)]
    attempts_dict[identifier] = attempts
    within_limit = len(attempts) < max_attempts
    if not within_limit:
        logger.warning(
            "Too many failed attempts",
            extra={
                "identifier": identifier,
                "attempt_count": len(attempts),
                "max_attempts": max_attempts,
            },
        )
    return within_limit

def limiter_key():
    """
    Generate a rate limit key based on the user's IP address and username.

    Returns:
        str: Rate limit key.
    """
    username = request.form.get("username", "")
    key = f"{get_remote_address()}:{username}"
    logger.debug("Generated rate limit key", extra={"key": key})
    return key

def log_failed_attempt(
    identifier: str, attempts_dict: Dict[str, List[datetime]]
) -> None:
    """
    Log a failed attempt for the given identifier.

    Args:
        identifier: The unique identifier (e.g., username or IP address).
        attempts_dict: Dictionary tracking failed attempts.
    """
    now = datetime.now()
    attempts_dict.setdefault(identifier, []).append(now)
    clean_failed_attempts(attempts_dict)
    logger.info(
        "Logged failed attempt",
        extra={
            "identifier": identifier,
            "timestamp": now,
            "total_attempts": len(attempts_dict[identifier]),
        },
    )
