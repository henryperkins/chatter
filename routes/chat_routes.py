"""
chat_routes.py

This module defines the routes for the chat interface, including
handling new chats, loading chats, deleting chats, and sending messages.
"""

import logging
import os
import json

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from chat_api import scrape_data
from chat_utils import generate_new_chat_id
from conversation_manager import ConversationManager
from database import get_db
from models import Chat, Model
from azure_config import get_azure_client, initialize_client_from_model

bp = Blueprint("chat", __name__)
conversation_manager = ConversationManager()
logger = logging.getLogger(__name__)


@bp.route("/")
@login_required
def index() -> str:
    """Redirect to the chat interface."""
    return redirect(url_for("chat.chat_interface"))


@bp.route("/new_chat", methods=["POST"])
@login_required
def new_chat_route() -> str:
    """Create a new chat and redirect to the chat interface."""
    chat_id = generate_new_chat_id()
    user_id = int(current_user.id)

    # Create a new chat in the database
    Chat.create(chat_id, user_id, "New Chat")
    session["chat_id"] = chat_id
    logger.info("New chat created with ID: %s", chat_id)
    return jsonify({"success": True, "chat_id": chat_id})


@bp.route("/chat_interface")
@login_required
def chat_interface() -> str:
    """Render the main chat interface page."""
    chat_id = session.get("chat_id")
    if not chat_id:
        return redirect(url_for("chat.new_chat_route"))

    messages = conversation_manager.get_context(chat_id)

    # Fetch models for the dropdown
    models = Model.get_all()

    return render_template(
        "chat.html", chat_id=chat_id, messages=messages, models=models
    )


@bp.route("/load_chat/<chat_id>")
@login_required
def load_chat(chat_id: str) -> dict:
    """Load and return the messages for a specific chat."""
    db = get_db()
    # Verify chat ownership
    chat = db.execute(
        "SELECT id FROM chats WHERE id = ? AND user_id = ?",
        (chat_id, current_user.id),
    ).fetchone()

    if not chat:
        logger.warning("Unauthorized access attempt to chat %s", chat_id)
        return jsonify({"error": "Chat not found or access denied"}), 403

    messages = conversation_manager.get_context(chat_id)

    return jsonify({"messages": messages})


@bp.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id: str) -> dict:
    """Delete a chat and its associated messages."""
    db = get_db()
    chat_to_delete = db.execute(
        "SELECT user_id FROM chats WHERE id = ?", (chat_id,)
    ).fetchone()

    if not chat_to_delete or int(chat_to_delete["user_id"]) != int(current_user.id):
        logger.warning(
            "Attempt to delete non-existent or unauthorized chat: %s", chat_id
        )
        return jsonify({"error": "Chat not found or access denied"}), 403

    db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    db.commit()

    logger.info("Chat %s deleted successfully", chat_id)
    return jsonify({"success": True})


@bp.route("/conversations", methods=["GET"])
@login_required
def get_conversations() -> dict:
    """Retrieve all conversations for the current user."""
    user_id = int(current_user.id)
    conversations = Chat.get_user_chats(user_id)
    return jsonify(conversations)


@bp.route("/scrape", methods=["POST"])
@login_required
def scrape() -> dict:
    """Handle web scraping requests."""
    data = request.get_json()
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query is required."}), 400

    try:
        response = scrape_data(query)
        return jsonify({"response": response})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Error during scraping: %s", str(e))
        return jsonify({"error": "An error occurred during scraping"}), 500


@bp.route("/chat", methods=["POST"])
@login_required
def handle_chat() -> dict:
    """Handle incoming chat messages and return responses."""
    logger.debug("Received chat message")
    chat_id = session.get("chat_id")
    if not chat_id:
        logger.error("Chat ID not found in session")
        return jsonify({"error": "Chat ID not found."}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request data"}), 400

    user_message = data.get("message")

    if not user_message:
        logger.error("Invalid request data: missing 'message' field")
        return jsonify({"error": "Message is required."}), 400

    # Check for special commands
    if user_message.startswith("what's the weather in") or user_message.startswith(
        "search for"
    ):
        try:
            model_response = scrape_data(user_message)
            messages = [{"role": "assistant", "content": model_response}]
            conversation_manager.clear_context(chat_id)
            for message in messages:
                conversation_manager.add_message(
                    chat_id, message["role"], message["content"]
                )
            return jsonify({"response": model_response})
        except ValueError as e:
            logger.error("Error in scraping: %s", str(e))
            return jsonify({"error": "Error processing special command."}), 500

    # Add the user message to the conversation history
    conversation_manager.add_message(chat_id, "user", user_message)

    try:
        # Retrieve the selected model or use the default
        selected_model_id = session.get("selected_model_id")
        model = Model.get_by_id(selected_model_id)

        if model:
            client, deployment_name, temperature, max_tokens, max_completion_tokens = (
                initialize_client_from_model(model.__dict__)
            )
        else:
            client, deployment_name = get_azure_client()
            default_model = Model.get_default()
            if default_model and default_model.requires_o1_handling:
                temperature = 1  # Set temperature to 1 for o1-preview
            else:
                temperature = 1.0  # Use default temperature
            max_tokens = None
            max_completion_tokens = 500

        messages = conversation_manager.get_context(chat_id)

        # Ensure no system message is included for o1-preview
        api_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if msg["role"] in ["user", "assistant"]
        ]

        # Prepare the parameters for the API call
        api_params = {
            "model": deployment_name,
            "messages": api_messages,
            "temperature": temperature,
        }

        if max_completion_tokens is not None:
            api_params["max_completion_tokens"] = max_completion_tokens

        # Include max_tokens only if it's not None and the model doesn't require o1 handling
        if max_tokens is not None and not (model and model.requires_o1_handling):
            api_params["max_tokens"] = max_tokens

        response = client.chat.completions.create(**api_params)

        # Process and log the model's response
        if response.choices and response.choices[0].message:
            model_response = response.choices[0].message.content
        else:
            model_response = "The assistant was unable to generate a response. Please try again or rephrase your input."
        logger.info("Response received from the model: %s", model_response)

        # Add the model's response to the conversation history
        conversation_manager.add_message(chat_id, "assistant", model_response)

        # Extract usage data
        usage_info = getattr(response, "usage", {})
        prompt_tokens = usage_info.get("prompt_tokens", 0)
        completion_tokens = usage_info.get("completion_tokens", 0)
        total_tokens = usage_info.get("total_tokens", 0)
        logger.info(
            "API usage - Prompt tokens: %d, Completion tokens: %d, Total tokens: %d",
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

        return jsonify({"response": model_response})

    except Exception as e:
        logger.exception(
            "An unexpected error occurred while handling the chat message."
        )
        return (
            jsonify({"error": "An unexpected error occurred. Please try again later."}),
            500,
        )


@bp.route("/upload", methods=["POST"])
@login_required
def upload_files() -> dict:
    """Handle file uploads."""
    try:
        if "file" not in request.files:
            return (
                jsonify({"success": False, "error": "No file part in the request"}),
                400,
            )

        files = request.files.getlist("file")
        if not files or files[0].filename == "":
            return jsonify({"success": False, "error": "No files selected"}), 400

        uploaded_files = []
        for file in files:
            filename = secure_filename(file.filename)
            if not filename:
                continue  # Skip files with invalid filenames
            file_path = os.path.join("uploads", current_user.username, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            uploaded_files.append(file_path)

        session["uploaded_files"] = uploaded_files
        return (
            jsonify(
                {
                    "success": True,
                    "files": [os.path.basename(f) for f in uploaded_files],
                }
            ),
            200,
        )
    except Exception as e:
        logger.exception("Error occurred during file upload")
        return (
            jsonify(
                {"success": False, "error": "An error occurred during file upload"}
            ),
            500,
        )
