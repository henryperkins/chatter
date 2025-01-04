import logging
import os
import uuid
import mimetypes
from typing import Union, Tuple

import bleach
from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
    current_app,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from chat_api import scrape_data
from chat_utils import generate_new_chat_id, count_tokens
from conversation_manager import ConversationManager
from database import get_db
from models import Chat, Model, UploadedFile
from azure_config import get_azure_client
import tiktoken

bp = Blueprint("chat", __name__)
conversation_manager = ConversationManager()
logger = logging.getLogger(__name__)

# Constants
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.py', '.js', '.md', '.jpg', '.png'}
ALLOWED_MIME_TYPES = {
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/x-python",
    "application/javascript",
    "text/markdown",
    "image/jpeg",
    "image/png",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file
MAX_TOTAL_FILE_SIZE = 50 * 1024 * 1024  # 50 MB for total files
MAX_FILE_CONTENT_LENGTH = 6000  # Characters
MAX_INPUT_TOKENS = 4000  # Azure OpenAI token limit

# Initialize tokenizer
encoding = tiktoken.encoding_for_model("gpt-4")  # Or whichever model you're using

# --- Helper Functions ---


def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def truncate_message(message, max_tokens):
    """Truncates a message to a specified number of tokens."""
    tokens = encoding.encode(message)
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens]
        truncated_message = encoding.decode(truncated_tokens)
        truncated_message += (
            "\n\n[Note: The input was too long and has been truncated.]"
        )
        return truncated_message
    return message


# --- Routes ---


@bp.route("/")
@login_required
def index() -> Response:
    """Redirect to the chat interface."""
    return redirect(url_for("chat.chat_interface"))


@bp.route("/new_chat", methods=["GET", "POST"])
@login_required
def new_chat_route() -> Response:
    """Create a new chat and return success JSON."""
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
def chat_interface() -> str:
    """Render the main chat interface page."""
    chat_id = session.get("chat_id")
    if not chat_id:
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        Chat.create(chat_id, user_id, "New Chat")
        session["chat_id"] = chat_id

    messages = conversation_manager.get_context(chat_id)
    models = Model.get_all()

    return render_template(
        "chat.html",
        chat_id=chat_id,
        messages=messages,
        models=models,
        now=datetime.now,
    )


@bp.route("/load_chat/<chat_id>")
@login_required
def load_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
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
    # Exclude 'system' messages from being sent to the frontend
    messages_to_send = [msg for msg in messages if msg["role"] != "system"]

    return jsonify({"messages": messages_to_send})


@bp.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
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
def get_conversations() -> Response:
    """Retrieve all conversations for the current user."""
    user_id = int(current_user.id)
    conversations = Chat.get_user_chats(user_id)
    return jsonify(conversations)


@bp.route("/scrape", methods=["POST"])
@login_required
def scrape() -> Union[Response, Tuple[Response, int]]:
    """Handle web scraping requests."""
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
    """Handle incoming chat messages and return AI responses."""
    logger.debug("Received chat message")
    chat_id = session.get("chat_id")
    if not chat_id:
        logger.error("Chat ID not found in session")
        return jsonify({"error": "Chat ID not found."}), 400

    # Retrieve message from form data
    user_message = request.form.get("message", "").strip()

    if not user_message and 'files[]' not in request.files:
        return jsonify({"error": "Message or files are required."}), 400

    # Handle uploaded files
    uploaded_files = request.files.getlist("files[]")
    included_files = []
    excluded_files = []

    for file in uploaded_files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)

            # Get MIME type
            mime_type = file.mimetype

            # Validate MIME type
            if mime_type not in ALLOWED_MIME_TYPES:
                logger.warning(f"File {filename} has disallowed MIME type {mime_type}.")
                excluded_files.append(filename)
                continue

            # Check file size
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)
            if file_length > MAX_FILE_SIZE:
                logger.warning(f"File {filename} exceeds the maximum size limit.")
                excluded_files.append(filename)
                continue

            # Save the file to the upload folder
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(file_path)
            except Exception as e:
                logger.error(f"Error saving file {filename}: {e}")
                excluded_files.append(filename)
                continue

            # Read file content if applicable
            if mime_type.startswith('text/'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                except Exception as e:
                    logger.error(f"Error reading file {filename}: {e}")
                    excluded_files.append(filename)
                    continue

                # Truncate file content if necessary
                truncated_content = truncate_message(file_content, MAX_FILE_CONTENT_LENGTH)

                # Add file content to conversation as a system message
                conversation_manager.add_message(chat_id, "system", f"Content of file '{filename}':\n{truncated_content}")

            else:
                logger.info(f"Skipping reading content for non-text file: {filename}")

            # Record the file as included
            included_files.append(filename)

            # Save file information to the database
            UploadedFile.create(chat_id, filename, file_path)
        else:
            excluded_files.append(file.filename)

    # Process user message
    if user_message:
        # Sanitize user input
        user_message = bleach.clean(user_message)
        conversation_manager.add_message(chat_id, "user", user_message)

    # Retrieve conversation history
    history = conversation_manager.get_context(chat_id)

    # Prepare messages for the AI model
    client, deployment_name = get_azure_client()
    api_params = {
        "model": deployment_name,
        "messages": history,
        "temperature": 1,
    }

    try:
        response = client.chat.completions.create(**api_params)
        model_response = (
            response.choices[0].message.content
            if response.choices and response.choices[0].message
            else "The assistant was unable to generate a response."
        )

        # Add assistant's response to conversation history
        conversation_manager.add_message(chat_id, "assistant", model_response)

        # Prepare response data
        response_data = {"response": model_response}
        if excluded_files:
            response_data["excluded_files"] = excluded_files

        return jsonify(response_data)

    except Exception as ex:
        logger.exception("Error during chat handling: %s", ex)
        return jsonify({"error": "An unexpected error occurred."}), 500
