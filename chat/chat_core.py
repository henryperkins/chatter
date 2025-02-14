"""
Core chat functionality and basic routes.
Handles main chat interface and initialization.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Union, Tuple, Dict, Any, Optional

from flask import (
    Blueprint, request, jsonify, render_template, 
    make_response, session, redirect, url_for
)
from flask.wrappers import Response as FlaskResponse
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from database import db_session
from sqlalchemy import text

from models.chat import Chat
from models.model import Model
from models.provider import Provider
from utils.encryption import decrypt_api_key, EncryptionError
from conversation_manager import conversation_manager
from chat.chat_utilities import generate_new_chat_id, init_upload_folder
from config import config_instance

# Logging setup
from logging_config import get_logger
logger = get_logger(__name__)

# Blueprint setup
chat_routes = Blueprint("chat", __name__, url_prefix="/chat")

# Initialize upload folder
init_upload_folder()

@chat_routes.route("/interface")
@login_required
def index() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Main chat interface route."""
    try:
        with db_session() as db:
            # Check if models exist
            model_count = db.scalar(text("SELECT COUNT(*) FROM models"))
            if not model_count:
                logger.warning("No models found - showing error message")
                return render_template(
                    "error.html",
                    error="No AI models are configured. Please contact your administrator.",
                    show_models_link=True
                ), 200

            # Get or create chat
            chat_id = session.get("chat_id", "")
            if not isinstance(chat_id, str):
                chat_id = str(chat_id)

            existing_chat = Chat.get_by_id(chat_id) if chat_id else None
            if not existing_chat:
                new_id = generate_new_chat_id()
                Chat.create(chat_id=new_id, user_id=current_user.id, title="New Chat")
                session["chat_id"] = new_id
                chat_id = new_id

            chat = Chat.get_by_id(chat_id)
            if not chat:
                return redirect(url_for("chat.index"))

            # Get model configuration
            model_obj = Chat.get_model(chat_id) if chat.model_id else Model.get_default()
            if not model_obj and chat.model_id:
                return render_template(
                    "error.html",
                    error="The model configuration is invalid."
                ), 500

            # Get Azure token if available
            azure_token = None
            if model_obj and model_obj.api_key:
                try:
                    azure_token = decrypt_api_key(
                        model_obj.api_key,
                        config_instance.ENCRYPTION_KEY
                    )
                except EncryptionError as e:
                    logger.error("Error decrypting Azure token: %s", str(e))
                    return render_template(
                        "error.html",
                        error="Configuration error: Unable to decrypt API key."
                    ), 500

            # Get messages and sanitize
            messages = conversation_manager.get_context(chat_id)
            for message in messages:
                if message["role"] == "user":
                    message["content"] = bleach.clean(message["content"])

            # Prepare chat config
            chat_config = {
                "chatId": chat_id,
                "csrfToken": generate_csrf(),
                "azureToken": azure_token or "",
                "userId": str(current_user.id),
                "modelSettings": model_obj.to_dict() if model_obj else {}
            }

            return render_template(
                "chat.html",
                chat_id=chat_id,
                chat_title=chat.title,
                model_name=model_obj.name if model_obj else "Default Model",
                current_model=model_obj,
                messages=messages,
                models=Model.get_all(),
                conversations=Chat.get_user_chats(current_user.id),
                now=datetime.now,
                today=datetime.now().strftime("%Y-%m-%d"),
                yesterday=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                azure_token=azure_token,
                CHAT_CONFIG=json.dumps(chat_config)
            )

    except Exception as e:
        logger.error("Error initializing chat interface: %s", str(e))
        return jsonify({"error": "Internal server error"}), 500


@chat_routes.route("/chat_interface", methods=["GET"])
@login_required
def chat_interface() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Secondary chat interface route for existing chats."""
    logger.debug("Current user: id=%s, role=%s", current_user.id, current_user.role)

    # Get chat ID from request or session
    chat_id = request.args.get("chat_id") or session.get("chat_id", "")
    if not isinstance(chat_id, str):
        chat_id = str(chat_id)

    if request.args.get("chat_id"):
        session["chat_id"] = chat_id

    # Create new chat if needed
    if not chat_id or not Chat.get_by_id(chat_id):
        chat_id = generate_new_chat_id()
        Chat.create(chat_id=chat_id, user_id=current_user.id, title="New Chat")
        session["chat_id"] = chat_id
        return redirect(url_for("chat.index"))

    chat = Chat.get_by_id(chat_id)
    if not chat:
        return redirect(url_for("chat.chat_interface"))

    try:
        # Get model and validate
        model_obj = Chat.get_model(chat_id) if chat.model_id else None
        if not model_obj and chat.model_id:
            return render_template(
                "error.html",
                error="The model configuration is invalid."
            ), 500

        # Get Azure token
        azure_token = None
        if model_obj and model_obj.api_key:
            try:
                azure_token = decrypt_api_key(
                    model_obj.api_key,
                    config_instance.ENCRYPTION_KEY
                )
            except EncryptionError as e:
                logger.error("Error decrypting Azure token: %s", str(e))
                return render_template(
                    "error.html",
                    error="Configuration error: Unable to decrypt API key."
                ), 500

        # Get messages
        messages = conversation_manager.get_context(chat_id)
        if not messages:
            # Add welcome messages
            conversation_manager.add_message(
                chat_id=chat_id,
                role="system",
                content="Welcome to Azure OpenAI Chat!"
            )
            conversation_manager.add_message(
                chat_id=chat_id,
                role="assistant",
                content="Hello! I'm ready to help. You can:\n"
                       "- Type a message to chat\n"
                       "- Upload files for analysis\n"
                       "- Change models using the dropdown\n"
                       "- Start a new chat with the + button"
            )
            messages = conversation_manager.get_context(chat_id)

        # Sanitize messages
        for message in messages:
            if message["role"] == "user":
                message["content"] = bleach.clean(message["content"])

        # Prepare chat config
        chat_config = {
            "chatId": chat_id,
            "csrfToken": generate_csrf(),
            "azureToken": azure_token or "",
            "userId": str(current_user.id),
            "modelSettings": model_obj.to_dict() if model_obj else {}
        }

        return render_template(
            "chat.html",
            chat_id=chat_id,
            chat_title=chat.title,
            model_name=model_obj.name if model_obj else "Default Model",
            current_model=model_obj,
            messages=messages,
            models=Model.get_all(),
            conversations=Chat.get_user_chats(current_user.id),
            now=datetime.now,
            today=datetime.now().strftime("%Y-%m-%d"),
            yesterday=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            azure_token=azure_token,
            CHAT_CONFIG=json.dumps(chat_config)
        )

    except Exception as e:
        logger.error("Error in chat interface: %s", str(e))
        return render_template(
            "error.html",
            error="An error occurred while loading the chat interface."
        ), 500
