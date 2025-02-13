"""
Statistics and monitoring functionality for chat system.
Handles usage tracking, logging, and analytics.
"""

import uuid
from datetime import datetime
from typing import Union, Tuple, Dict, Any

from flask import Blueprint, request, jsonify, session
from flask.wrappers import Response as FlaskResponse
from flask_login import login_required, current_user

from models.chat import Chat
from models.model import Model
from conversation_manager import conversation_manager
from chat.chat_utilities import validate_chat_access

# Logging setup
from logging_config import get_logger
logger = get_logger(__name__)
user_logger = get_logger("user_actions")

@login_required
def get_chat_stats(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Get comprehensive chat statistics.
    
    Args:
        chat_id: ID of the chat to analyze
        
    Returns:
        JSON response with chat statistics
    """
    if not validate_chat_access(chat_id, current_user.id):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            return jsonify({"error": "Model not found"}), 404

        # Get detailed stats
        stats = conversation_manager.get_usage_stats(chat_id)

        return jsonify({
            "success": True,
            "stats": {
                "total_tokens": stats["total_tokens"],
                "token_breakdown": stats["token_breakdown"],
                "total_messages": stats["total_messages"],
                "message_counts": {
                    "user": stats["user_messages"],
                    "assistant": stats["assistant_messages"],
                    "system": stats["system_messages"]
                },
                "average_tokens_per_message": stats["average_tokens_per_message"],
                "largest_message": stats["largest_message"],
                "model_limits": {
                    "max_tokens": model_obj.max_tokens,
                    "max_completion_tokens": model_obj.max_completion_tokens,
                    "tokens_left": stats["model_limits"]["tokens_left"],
                    "tokens_used_percentage": stats["model_limits"]["tokens_used_percentage"]
                }
            }
        })
    except Exception as e:
        logger.error(f"Error getting chat stats: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@login_required
def log_client_event() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Handle client-side event logging."""
    try:
        log_data = request.get_json()
        if not log_data:
            return jsonify({"error": "No log data provided"}), 400

        # Enrich log data
        log_data.update({
            "user_id": current_user.id,
            "session_id": session.get("id"),
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
            "url": request.headers.get("Referer"),
            "chat_id": log_data.get("chat_id") or session.get("chat_id")
        })

        user_logger.info("Client Event:", extra={"client_event": log_data})
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error logging client event: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@login_required
def log_client_error() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Handle client-side error logging."""
    try:
        error_data = request.get_json()
        if not error_data:
            return jsonify({"error": "No error data provided"}), 400

        # Enrich error data
        error_data.update({
            "user_id": current_user.id,
            "session_id": session.get("id"),
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
            "url": request.headers.get("Referer"),
            "chat_id": error_data.get("chatId") or session.get("chat_id")
        })

        user_logger.error("Client Error:", extra={"client_error": error_data})
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error logging client error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

def get_token_usage(chat_id: str) -> Dict[str, Any]:
    """
    Get detailed token usage statistics for a chat.
    
    Args:
        chat_id: ID of the chat to analyze
        
    Returns:
        Dict containing token usage statistics
    """
    try:
        stats = conversation_manager.get_usage_stats(chat_id)
        model_obj = Chat.get_model(chat_id)
        
        if not model_obj:
            return {
                "error": "Model not found",
                "total_tokens": 0,
                "available_tokens": 0,
                "percentage_used": 0
            }
            
        max_tokens = model_obj.max_tokens
        total_tokens = stats["total_tokens"]
        available_tokens = max(0, max_tokens - total_tokens)
        percentage_used = min(100, (total_tokens / max_tokens) * 100)
        
        return {
            "total_tokens": total_tokens,
            "available_tokens": available_tokens,
            "percentage_used": percentage_used,
            "token_breakdown": stats["token_breakdown"]
        }
        
    except Exception as e:
        logger.error(f"Error getting token usage: {str(e)}")
        return {
            "error": str(e),
            "total_tokens": 0,
            "available_tokens": 0,
            "percentage_used": 0
        }

def track_token_usage(chat_id: str, tokens_used: int) -> bool:
    """
    Track token usage for a chat session.
    
    Args:
        chat_id: ID of the chat session
        tokens_used: Number of tokens used
        
    Returns:
        True if tracking was successful, False otherwise
    """
    try:
        # Get current stats and update token count
        stats = conversation_manager.get_usage_stats(chat_id)
        stats["total_tokens"] += tokens_used
        return True
    except Exception as e:
        logger.error(f"Error tracking token usage: {str(e)}")
        return False

def get_chat_metrics(chat_id: str) -> Dict[str, Any]:
    """
    Get key metrics for a chat session.
    
    Args:
        chat_id: ID of the chat session
        
    Returns:
        Dictionary containing chat metrics
    """
    try:
        stats = conversation_manager.get_usage_stats(chat_id)
        return {
            "total_messages": stats["total_messages"],
            "average_tokens_per_message": stats["average_tokens_per_message"],
            "largest_message": stats["largest_message"]
        }
    except Exception as e:
        logger.error(f"Error getting chat metrics: {str(e)}")
        return {
            "error": str(e)
        }

def generate_usage_report(chat_id: str) -> Dict[str, Any]:
    """
    Generate a comprehensive usage report for a chat session.
    
    Args:
        chat_id: ID of the chat to generate report for
        
    Returns:
        Dictionary containing formatted usage report data with sections for:
        - Token usage
        - Message statistics
        - Model information
        - Session details
    """
    try:
        # Get basic statistics
        stats = conversation_manager.get_usage_stats(chat_id)
        model_obj = Chat.get_model(chat_id)
        
        if not model_obj:
            return {
                "error": "Model not found",
                "report": {}
            }
            
        # Format report data
        report = {
            "chat_id": chat_id,
            "model": {
                "name": model_obj.name,
                "max_tokens": model_obj.max_tokens,
                "max_completion_tokens": model_obj.max_completion_tokens
            },
            "token_usage": {
                "total_tokens": stats["total_tokens"],
                "token_breakdown": stats["token_breakdown"],
                "tokens_remaining": max(0, model_obj.max_tokens - stats["total_tokens"]),
                "percentage_used": min(100, (stats["total_tokens"] / model_obj.max_tokens) * 100)
            },
            "message_statistics": {
                "total_messages": stats["total_messages"],
                "message_types": {
                    "user": stats["user_messages"],
                    "assistant": stats["assistant_messages"],
                    "system": stats["system_messages"]
                },
                "average_tokens_per_message": stats["average_tokens_per_message"],
                "largest_message": stats["largest_message"]
            },
            "session_details": {
                "start_time": stats.get("start_time"),
                "duration": stats.get("duration"),
                "active": stats.get("active", False)
            }
        }
        
        return report
        
    except Exception as e:
        logger.error(f"Error generating usage report: {str(e)}")
        return {
            "error": str(e),
            "report": {}
        }