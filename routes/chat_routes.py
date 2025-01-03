"""
chat_routes.py

This module defines the routes for the chat interface, including
handling new chats, loading chats, deleting chats, and sending messages.
It also includes file upload functionality and integrates uploaded files
into the chat context.
"""

import logging
import os
import uuid
import imghdr
from typing import Union, Tuple
from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from markupsafe import escape

from chat_api import scrape_data
from chat_utils import generate_new_chat_id, count_tokens
from conversation_manager import ConversationManager
from database import get_db
from models import Chat, Model
from azure_config import get_azure_client, initialize_client_from_model

bp = Blueprint("chat", __name__)
conversation_manager = ConversationManager()
logger = logging.getLogger(__name__)

# Constants
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".py", ".js", ".md", ".jpg", ".png"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit
MAX_FILE_CONTENT_LENGTH = 6000  # Characters
MAX_INPUT_TOKENS = 4000 # Tokens


@bp.route("/")
@login_required
def index() -> Response:
    """
    Redirect to the chat interface.
    """
    return redirect(url_for("chat.chat_interface"))


@bp.route("/new_chat", methods=["GET", "POST"])
@login_required
def new_chat_route() -> Response:
    """
    Create a new chat and return success JSON.
    """
    chat_id = generate_new_chat_id()
    user_id = int(current_user.id)

    Chat.create(chat_id, user_id, "New Chat")
    session["chat_id"] = chat_id
    logger.info("New chat created with ID: %s", chat_id)

    if request.method == "POST":
        return jsonify({"success": True, "chat_id": chat_id})
    return render_template("new_chat.html")


@bp.route("/chat_interface")
@login_required
def chat_interface() -> Union[str, Response]:
    """
    Render the main chat interface page.
    Returns an HTML template as a string (implicitly converted to a Response).
    """
    chat_id = session.get("chat_id")
    if not chat_id:
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        Chat.create(chat_id, user_id, "New Chat")
        session["chat_id"] = chat_id
        logger.info("New chat created with ID: %s", chat_id)

    messages = conversation_manager.get_context(chat_id)
    models = Model.get_all()

    return render_template(
        "chat.html", chat_id=chat_id, messages=messages, models=models
    )


@bp.route("/load_chat/<chat_id>")
@login_required
def load_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """
    Load and return the messages for a specific chat.
    """
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
    # Exclude 'system' messages from being sent to the frontend
    messages_to_send = [msg for msg in messages if msg['role'] != 'system']

    return jsonify({"messages": messages_to_send})


@bp.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """
    Delete a chat and its associated messages.
    """
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
def get_conversations() -> Response:
    """
    Retrieve all conversations for the current user.
    """
    user_id = int(current_user.id)
    conversations = Chat.get_user_chats(user_id)
    return jsonify(conversations)


@bp.route("/scrape", methods=["POST"])
@login_required
def scrape() -> Union[Response, Tuple[Response, int]]:
    """
    Handle web scraping requests.
    """
    data = request.get_json()
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query is required."}), 400

    try:
        response = scrape_data(query)
        return jsonify({"response": response})
    except ValueError as ex:
        logger.error("ValueError during scraping: %s", ex)
        return jsonify({"error": str(ex)}), 400
    except Exception as ex:
        logger.error("Error during scraping: %s", str(ex))
        return jsonify({"error": "An error occurred during scraping"}), 500


@bp.route("/chat", methods=["POST"])
@login_required
def handle_chat() -> Union[Response, Tuple[Response, int]]:
    """
    Handle incoming chat messages and return AI responses.
    """
    logger.debug("Received chat message")
    chat_id = session.get("chat_id")
    if not chat_id:
        logger.error("Chat ID not found in session")
        return jsonify({"error": "Chat ID not found."}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request data"}), 400

    user_message = data.get("message")

    # Input sanitization
    if not user_message:
        return jsonify({"error": "Message cannot be empty."}), 400
    if len(user_message) > 1000:
        return jsonify({"error": "Message is too long. Max length is 1000 chars."}), 400

    user_message = escape(user_message)

    try:
        # Retrieve uploaded file contents associated with this chat
        uploaded_contents = session.get('uploaded_files_content', {}).get(chat_id, [])

        # Prepare the combined message
        combined_message = user_message
        for file_info in uploaded_contents:
            filename = escape(file_info['filename'])
            content = escape(file_info['content'])

            # Append the file content to the user's message
            combined_message += f"\n\n[Content from file '{filename}']\n{content}"
        
        combined_message_tokens = count_tokens(combined_message)
        if combined_message_tokens > MAX_INPUT_TOKENS:
            return jsonify({"error": "The combined message exceeds the maximum allowed length."}), 400

        # Clear the uploaded contents after use
        session['uploaded_files_content'][chat_id] = []

        # For o1-preview, only one user message is allowed, so we send the combined 
message
        api_messages = [{"role": "user", "content": combined_message}]

        # Initialize the model parameters
        client, deployment_name = get_azure_client()
        temperature = 1  # o1-preview requires temperature to be 1
        max_completion_tokens = 500  # Adjust as needed or retrieve from model config

        # Prepare the API parameters
        api_params = {
            "model": deployment_name,
            "messages": api_messages,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
        }

        # Send the request to the AI model
        response = client.chat.completions.create(**api_params)

        # Extract the model response
        model_response = (
            response.choices[0].message.content
            if response.choices and response.choices[0].message
            else "The assistant was unable to generate a response."
        )
        model_response = escape(model_response)

        logger.info("Response from the model: %s", model_response)

        # Add the user's message and model's response to the conversation history
        conversation_manager.add_message(chat_id, "user", user_message)
        conversation_manager.add_message(chat_id, "assistant", model_response)

        # Log usage
        usage_info = getattr(response, "usage", None)
        prompt_tokens = usage_info.prompt_tokens if usage_info else 0
        completion_tokens = usage_info.completion_tokens if usage_info else 0
        total_tokens = usage_info.total_tokens if usage_info else 0
        logger.info(
            "API usage - Prompt: %d, Completion: %d, Total: %d",
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

        return jsonify({"response": model_response})

    except Exception as ex:
        logger.exception(
            "An unexpected error occurred while handling the chat message: %s", ex
        )
        return (
            jsonify({"error": "An unexpected error occurred. Please try again later."}),
            500,
        )


@bp.route("/upload", methods=["POST"])
@login_required
def upload_files() -> Union[Response, Tuple[Response, int]]:
    """
    Handle file uploads securely and store file contents for use in chats.
    """
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file part in the request."}), 400

        files = request.files.getlist("file")
        if not files or files[0].filename == "":
            return jsonify({"success": False, "error": "No files selected."}), 400

        uploaded_files = []
        uploaded_contents = []

        for file in files:
            if not file.filename:
                continue

            filename = secure_filename(file.filename)
            if not filename:
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return jsonify({"success": False, "error": f"Invalid file type: {filename}."}), 400

            file_content = file.read()
            file_size = len(file_content)
            if file_size > MAX_FILE_SIZE:
                return jsonify({"success": False, "error": f"File too large: {filename}."}), 400

            if ext in {".jpg", ".png"}:
                image_type = imghdr.what(None, h=file_content)
                if image_type not in {"jpeg", "png"}:
                    return jsonify({"success": False, "error": f"Invalid image file: {filename}."}), 400

            user_directory = os.path.join("uploads", str(current_user.id))
            os.makedirs(user_directory, exist_ok=True)

            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(user_directory, unique_filename)
            with open(file_path, "wb") as f:
                f.write(file_content)

            uploaded_files.append(unique_filename)

            if ext in {".txt", ".pdf", ".docx", ".py", ".js", ".md"}:
                try:
                    file_text = file_content.decode('utf-8', errors='ignore')
                    if len(file_text) > MAX_FILE_CONTENT_LENGTH:
                        file_text = file_text[:MAX_FILE_CONTENT_LENGTH] + "\n...[Content truncated]"
                    uploaded_contents.append({"filename": filename, "content": file_text})
                except Exception as e:
                    logger.warning(f"Could not decode file {filename}: {e}")

        chat_id = session.get('chat_id')
        if not chat_id:
            chat_id = generate_new_chat_id()
            user_id = int(current_user.id)
            Chat.create(chat_id, user_id, "New Chat")
            session['chat_id'] = chat_id

        if 'uploaded_files_content' not in session:
            session['uploaded_files_content'] = {}
        session['uploaded_files_content'][chat_id] = uploaded_contents

        return jsonify({"success": True, "files": uploaded_files}), 200

    except Exception as ex:
        logger.exception("Error during file upload: %s", ex)
        return jsonify({"success": False, "error": "An error occurred during file upload."}), 500