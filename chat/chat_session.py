"""
Session and chat management functionality.
Handles chat creation, deletion, and updates.
"""

import uuid
import bleach
from typing import Union, Tuple, Dict, Any

from flask import Blueprint, request, jsonify, session
from flask.wrappers import Response as FlaskResponse
from flask_login import login_required, current_user

from models.chat import Chat
from models.model import Model
from conversation_manager import conversation_manager
from chat_utils import validate_chat_access, generate_new_chat_id

# Logging setup
from logging_config import get_logger
logger = get_logger(__name__)

@login_required
def new_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Create a new chat session."""
    try:
        chat_id = generate_new_chat_id()
        Chat.create(chat_id=chat_id, user_id=current_user.id, title="New Chat")
        
        # Update session
        session["chat_id"] = chat_id
        
        return jsonify({
            "success": True,
            "chat_id": chat_id
        })
    except Exception as e:
        logger.error(f"Error creating new chat: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@login_required
def delete_chat(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Soft-delete a chat session.
    
    Args:
        chat_id: ID of the chat to delete
    """
    logger.debug(f"Received request to delete chat_id: {chat_id}")
    
    if not validate_chat_access(chat_id, current_user.id):
        logger.warning(f"Unauthorized delete attempt for chat {chat_id}")
        return jsonify({"error": "Chat not found or access denied"}), 403
        
    try:
        Chat.soft_delete(chat_id)
        logger.info(f"Chat {chat_id} deleted successfully")
        
        # Clear session if deleted chat was current
        if session.get("chat_id") == chat_id:
            session.pop("chat_id", None)
            
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {str(e)}")
        return jsonify({"error": "Failed to delete chat"}), 500

@login_required
def update_chat_title(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Update the title of a chat session.
    
    Args:
        chat_id: ID of the chat to update
    """
    logger.debug(f"Received request to update title for chat_id: {chat_id}")
    
    if not validate_chat_access(chat_id, current_user.id):
        return jsonify({"error": "Chat not found or access denied"}), 403

    data = request.get_json() or {}
    title = bleach.clean(data.get("title", "").strip())
    
    if not title or len(title) > 100:
        return jsonify({
            "error": "Title is required and must be under 100 characters"
        }), 400

    try:
        Chat.update_title(chat_id, title)
        logger.info(f"Chat title updated for chat_id: {chat_id}")
        return jsonify({"success": True})
    except Exception as e:
        logger.exception(f"Error updating chat title: {str(e)}")
        return jsonify({"error": "Failed to update chat title"}), 500

@login_required
def update_model() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Update chat model configuration."""
    try:
        data = request.get_json() or {}
        chat_id = data.get("chat_id")
        model_id = data.get("model_id")

        if not chat_id or not model_id:
            return jsonify({"error": "Missing required parameters"}), 400

        if not validate_chat_access(chat_id, current_user.id):
            return jsonify({"error": "Unauthorized"}), 403

        Chat.update_model_id(chat_id, model_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating model: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@login_required
def get_chat_context(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Get the current conversation context for a chat.
    
    Args:
        chat_id: ID of the chat to get context for
    """
    if not validate_chat_access(chat_id, current_user.id):
        return jsonify({"error": "Unauthorized access to chat"}), 403
        
    try:
        messages = conversation_manager.get_context(chat_id)
        
        # Sanitize user messages
        for msg in messages:
            if msg["role"] == "user":
                msg["content"] = bleach.clean(msg["content"])
                
        return jsonify({
            "success": True,
            "messages": messages
        })
    except Exception as e:
        logger.error(f"Error getting chat context: {str(e)}")
        return jsonify({"error": "Failed to get chat context"}), 500

def get_user_chats() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Get all chats for the current user."""
    try:
        chats = Chat.get_user_chats(current_user.id)
        return jsonify({
            "success": True,
            "chats": [{
                "id": chat.id,
                "title": chat.title,
                "created_at": chat.created_at.isoformat(),
                "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
                "model": {
                    "id": chat.model.id,
                    "name": chat.model.name
                } if chat.model else None
            } for chat in chats]
        })
    except Exception as e:
        logger.error(f"Error getting user chats: {str(e)}")
        return jsonify({"error": "Failed to get user chats"}), 500