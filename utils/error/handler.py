import logging
from typing import Tuple, Dict, Any
from flask import jsonify

logger = logging.getLogger(__name__)


def handle_error(error: Exception, message: str = "An error occurred") -> Tuple[Dict[str, Any], int]:
    """
    Centralized error handling utility.
    
    Args:
        error: The exception that occurred
        message: Optional custom error message
        
    Returns:
        Tuple containing JSON response and HTTP status code
    """
    logger.error(f"{message}: {error}")
    return jsonify({"success": False, "error": str(error)}), 500