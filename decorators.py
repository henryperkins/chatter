# decorators.py

"""Decorators for authentication and authorization."""

import functools
from typing import Callable, TypeVar, cast

from flask import abort, request, current_app
import logging
from flask_login import current_user
RT = TypeVar("RT")  # Return type for the decorated function

# Configure logging
logger = logging.getLogger(__name__)
RT = TypeVar("RT")  # Return type for the decorated function

def admin_required(func: Callable[..., RT]) -> Callable[..., RT]:
    """Decorator to ensure that only admin users can access a route.

    Args:
        func: The function to be decorated

    Returns:
        A wrapped function that checks for admin privileges before execution

    Raises:
        403: If the current user is not an admin
    """
    @functools.wraps(func)
    def decorated_function(*args: object, **kwargs: object) -> RT:
        if not current_user.is_authenticated:
            logger.warning(f"Unauthorized access attempt by unauthenticated user: {request.path}")
            abort(403, description="You need to be logged in to access this resource.")
        if current_user.role != "admin":
            logger.warning(f"Unauthorized access attempt by non-admin user: {current_user.username}")
            abort(403, description="You don't have sufficient privileges to access this resource.")
        return cast(RT, func(*args, **kwargs))
    return decorated_function
