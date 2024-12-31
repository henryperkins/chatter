"""
chat_routes.py

This module defines the routes for the chat interface, including
handling new chats, loading chats, deleting chats, and sending messages.
"""

import logging
import os

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
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


@bp.route("/new-chat", methods=["GET"])
@login_required
def new_chat_page() -> str:
    """Render the new chat page."""
    return render_template("new_chat.html")


@bp.route("/")
@login_required
def index() -> str:
    """Redirect to the chat interface."""
    return redirect(url_for("chat.chat_interface"))


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


@bp.route("/new_chat", methods=["GET"])
@login_required
def new_chat_route() -> str:
    """Create a new chat and redirect to the chat interface."""
    chat_id = generate_new_chat_id()
    user_id = int(current_user.id)

    # Create a new chat in the database
    Chat.create(chat_id, user_id, "New Chat")
    session["chat_id"] = chat_id
    logger.info("New chat created with ID: %s", chat_id)
    return redirect(url_for("chat.chat_interface"))


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
            temperature = 1.0
            max_tokens = None
            max_completion_tokens = 500

        messages = conversation_manager.get_context(chat_id)

        # Ensure no system message is included for o1-preview
        api_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if msg["role"] in ["user", "assistant"]
        ]

        response = client.chat.completions.create(
            model=deployment_name,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            max_completion_tokens=max_completion_tokens,
        )

        model_response = (
            response.choices[0].message.content
            if response.choices[0].message
            else "The assistant was unable to generate a response. Please try again or rephrase your input."
        )
        logger.info("Response received from the model: %s", model_response)

        # Add the model's response to the conversation history
        conversation_manager.add_message(chat_id, "assistant", model_response)

        return jsonify({"response": model_response})

    except Exception as e:
        error_message = f"Unexpected Error: {str(e)}"
        logger.error(error_message)
        return jsonify({"error": error_message}), 500


@bp.route("/upload", methods=["POST"])
@login_required
def upload_files() -> dict:
    """Handle file uploads."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    files = request.files.getlist("file")
    if not files:
        return jsonify({"success": False, "error": "No files selected"}), 400

    uploaded_files = []
    for file in files:
        if file.filename == "":
            return jsonify({"success": False, "error": "No selected file"}), 400
        if file:
            filename = secure_filename(file.filename)
            if not filename:
                continue
            file_path = os.path.join("uploads", current_user.username, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            uploaded_files.append(file_path)

    # Store the uploaded file paths in the session
    session["uploaded_files"] = uploaded_files

    return (
        jsonify(
            {
                "success": True,
                "files": [
                    secure_filename(file.filename)
                    for file in files
                    if secure_filename(file.filename)
                ],
            }
        ),
        200,
    )
