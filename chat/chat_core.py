"""
Refactored chat blueprint code for handling:
- Main chat interface
- Secondary interface route
- Shared logic for retrieving or creating chats, loading model configs, etc.
"""

import os
import json
import bleach
from datetime import datetime, timedelta
from typing import Union, Tuple, Dict, Any, Optional

from flask import (
    Blueprint, request, jsonify, render_template,
    make_response, session, redirect, url_for
)
from flask.wrappers import Response as FlaskResponse
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import text

from database import db_session
from models.provider import Provider
from models.model import Model
from utils.encryption import decrypt_api_key, EncryptionError
from conversation_manager import conversation_manager
from chat.chat_utilities import generate_new_chat_id, init_upload_folder
from config import config_instance

# Logging setup
from logging_config import get_logger
logger = get_logger(__name__)

# Blueprint setup
chat_routes = Blueprint("chat", __name__, url_prefix="/chat")

# Initialize upload folder for file uploads
init_upload_folder()


def _get_or_create_chat(chat_id: Optional[str], user_id: int) -> Chat:
    """
    Retrieve an existing chat by chat_id or create a new one if not found.
    Returns the Chat object.
    """
    if chat_id:
        existing_chat = Chat.get_by_id(chat_id)
        if existing_chat:
            return existing_chat

    new_id = generate_new_chat_id()
    Chat.create(id=new_id, user_id=user_id, title="New Chat")
    return Chat.get_by_id(new_id)


def _load_chat_context(chat_id: Optional[str], user_id: int) -> Dict[str, Any]:
    """
    Loads or creates the necessary data to render a chat interface:
      - Chat record
      - Model configuration (and default if missing)
      - Decrypted API key (e.g., azure_token)
      - Chat messages (creates initial welcome messages if none exist)
      - Sanitizes user messages with bleach.
    Raises exceptions for serious issues like encryption errors or invalid models.
    """
    # 1. Retrieve or create the Chat
    chat = _get_or_create_chat(chat_id, user_id)

    # 2. Retrieve the associated model or the default model
    model_obj = Model.get_by_id(chat.model_id) if chat.model_id else Model.get_default()
    if not model_obj:
        raise ValueError("No model configured and no default model available")

    # 3. Decrypt the stored API key if available
    azure_token = ""
    if model_obj and model_obj.api_key:
        try:
            azure_token = decrypt_api_key(
                model_obj.api_key,
                config_instance.ENCRYPTION_KEY
            )
        except EncryptionError as exc:
            raise RuntimeError(f"Error decrypting API key: {str(exc)}")

    # 4. Load conversation messages; create welcome if none exist
    messages = conversation_manager.get_context(chat.id)
    if not messages:
        # If you have a method that initializes the conversation, call it
        conversation_manager.add_message(
            chat_id=chat.id,
            role="system",
            content="Welcome to Azure OpenAI Chat!"
        )
        conversation_manager.add_message(
            chat_id=chat.id,
            role="assistant",
            content=(
                "Hello! I'm ready to help. You can:\n"
                "- Type a message to chat\n"
                "- Upload files for analysis\n"
                "- Change models using the dropdown\n"
                "- Start a new chat with the + button"
            )
        )
        messages = conversation_manager.get_context(chat.id)

    # 5. Sanitize user messages to prevent XSS
    for msg in messages:
        if msg["role"] == "user":
            msg["content"] = bleach.clean(msg["content"])

    return {
        "chat": chat,
        "model_obj": model_obj,
        "azure_token": azure_token,
        "messages": messages
    }


@chat_routes.route("/interface")
@login_required
def index() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Main chat interface route:
      - Checks for model availability
      - Gets or creates chat (by session['chat_id'])
      - Loads messages, model config, etc.
      - Renders the chat interface
    """
    try:
        # Ensure at least one model is defined (optional check)
        with db_session() as db:
            model_count = db.scalar(text("SELECT COUNT(*) FROM models"))
            if not model_count:
                logger.warning("No models found - showing error message")
                return make_response(
                    render_template(
                        "error.html",
                        error="No AI models are configured. Please contact your administrator.",
                        show_models_link=True
                    )
                ), 200

        # Retrieve chat_id from session
        chat_id = session.get("chat_id", "")
        # Convert to str just to be safe
        if not isinstance(chat_id, str):
            chat_id = str(chat_id)

        # Load the chat context (chat, model, token, messages)
        context_data = _load_chat_context(chat_id, current_user.id)

        # Save updated chat_id to session (in case a new one was created)
        session["chat_id"] = context_data["chat"].id  # Use 'id' field as chat_id

        # Prepare front-end config
        chat_config = {
            "chatId": context_data["chat"].chat_id,
            "csrfToken": generate_csrf(),
            "azureToken": context_data["azure_token"],
            "userId": str(current_user.id),
            "modelSettings": (
                context_data["model_obj"].to_dict()
                if context_data["model_obj"]
                else {}
            )
        }

        return render_template(
            "chat.html",
            chat_id=context_data["chat"].chat_id,
            chat_title=context_data["chat"].title,
            model_name=(
                context_data["model_obj"].name
                if context_data["model_obj"]
                else "Default Model"
            ),
            current_model=context_data["model_obj"],
            messages=context_data["messages"],
            models=Model.get_all(),
            conversations=Chat.get_user_chats(current_user.id),
            now=datetime.now,
            today=datetime.now().strftime("%Y-%m-%d"),
            yesterday=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            azure_token=context_data["azure_token"],
            CHAT_CONFIG=json.dumps(chat_config)
        )

    except ValueError as ve:
        # Example for model or config errors
        logger.error("Value error in chat interface: %s", str(ve))
        return render_template("error.html", error=str(ve)), 500
    except RuntimeError as re:
        # Example for encryption errors
        logger.error("Runtime error in chat interface: %s", str(re))
        return render_template("error.html", error=str(re)), 500
    except Exception as e:
        logger.error("Error initializing chat interface: %s", str(e), exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@chat_routes.route("/chat_interface", methods=["GET"])
@login_required
def chat_interface() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Secondary route for loading the existing chat interface with a given chat_id.
    - If 'chat_id' is missing or invalid, a new chat session is created.
    - Renders chat.html with relevant context.
    """
    try:
        logger.debug("Current user: id=%s, role=%s", current_user.id, current_user.role)

        # Retrieve chat ID from query param or session
        chat_id = request.args.get("chat_id") or session.get("chat_id", "")
        if not isinstance(chat_id, str):
            chat_id = str(chat_id)

        # If an explicit chat_id is provided, store it in the session
        if request.args.get("chat_id"):
            session["chat_id"] = chat_id

        # Load the chat context
        context_data = _load_chat_context(chat_id, current_user.id)
        # In case a new one was created
        session["chat_id"] = context_data["chat"].chat_id

        # Prepare front-end config
        chat_config = {
            "chatId": context_data["chat"].chat_id,
            "csrfToken": generate_csrf(),
            "azureToken": context_data["azure_token"],
            "userId": str(current_user.id),
            "modelSettings": (
                context_data["model_obj"].to_dict()
                if context_data["model_obj"]
                else {}
            )
        }

        return render_template(
            "chat.html",
            chat_id=context_data["chat"].chat_id,
            chat_title=context_data["chat"].title,
            model_name=(
                context_data["model_obj"].name
                if context_data["model_obj"]
                else "Default Model"
            ),
            current_model=context_data["model_obj"],
            messages=context_data["messages"],
            models=Model.get_all(),
            conversations=Chat.get_user_chats(current_user.id),
            now=datetime.now,
            today=datetime.now().strftime("%Y-%m-%d"),
            yesterday=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            azure_token=context_data["azure_token"],
            CHAT_CONFIG=json.dumps(chat_config)
        )

    except ValueError as ve:
        logger.error("Value error in /chat_interface: %s", str(ve))
        return render_template("error.html", error=str(ve)), 500
    except RuntimeError as re:
        logger.error("Runtime error in /chat_interface: %s", str(re))
        return render_template("error.html", error=str(re)), 500
    except Exception as e:
        logger.error("Error in /chat_interface for chat_id=%s: %s", chat_id, str(e), exc_info=True)
        return render_template(
            "error.html",
            error="An error occurred while loading the chat interface."
        ), 500
