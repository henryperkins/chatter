```python
import logging
import os
import uuid
import imghdr
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
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from markupsafe import escape
from datetime import datetime
from chat_api import scrape_data, get_azure_response
from chat_utils import generate_new_chat_id, count_tokens
from conversation_manager import ConversationManager
from database import get_db
from models import Chat, Model
from azure_config import get_azure_client
import tiktoken

bp = Blueprint("chat", __name__)
conversation_manager = ConversationManager()
logger = logging.getLogger(__name__)

# Constants
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".py", ".js", ".md", ".jpg", ".png"}
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
    """
    Handle incoming chat messages, integrate uploaded files, and return AI responses.
    """
    logger.debug("Received chat message")
    chat_id = session.get("chat_id")
    if not chat_id:
        logger.error("Chat ID not found in session")
        return jsonify({"error": "Chat ID not found."}), 400

    data = request.form
    user_message = data.get("message", "").strip()
    uploaded_files = request.files.getlist("files[]")

    # Validate user input
    if not user_message and not uploaded_files:
        return jsonify({"error": "Message cannot be empty."}), 400

    # Sanitize user message
    user_message = bleach.clean(user_message)

    try:
        file_contents = []
        excluded_files = []
        total_size = 0

        for uploaded_file in uploaded_files:
            filename = secure_filename(uploaded_file.filename)
            if not filename:
                continue

            # Validate MIME type
            if uploaded_file.mimetype not in ALLOWED_MIME_TYPES:
                excluded_files.append(filename)
                logger.warning(
                    f"File {filename} has an invalid MIME type: {uploaded_file.mimetype}"
                )
                continue

            file_content = uploaded_file.read()
            file_size = len(file_content)
            total_size += file_size

            # Validate file size
            if file_size > MAX_FILE_SIZE:
                excluded_files.append(filename)
                logger.warning(f"File {filename} exceeds the 10MB limit.")
                continue

            # Validate total file size
            if total_size > MAX_TOTAL_FILE_SIZE:
                return (
                    jsonify(
                        {
                            "error": "Total size of all uploaded files exceeds 50MB limit."
                        }
                    ),
                    400,
                )

            try:
                # Attempt to decode as UTF-8
                content = file_content.decode("utf-8", errors="ignore")

                # Sanitize content using bleach, allowing only code-related tags and specific attributes
                allowed_tags = [
                    "code",
                    "pre",
                    "b",
                    "i",
                    "u",
                    "strike",
                    "br",
                    "p",
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "ul",
                    "ol",
                    "li",
                    "a",
                    "img",
                ]
                allowed_attributes = {
                    "a": ["href", "title", "target"],
                    "img": ["src", "alt"],
                }
                content = bleach.clean(
                    content, tags=allowed_tags, attributes=allowed_attributes
                )

                # Truncate if necessary
                if len(content) > MAX_FILE_CONTENT_LENGTH:
                    content = (
                        content[:MAX_FILE_CONTENT_LENGTH] + "\n...[Content truncated]"
                    )

                logger.debug(f"Processed file '{filename}' with size {file_size} bytes.")

                file_contents.append({"filename": filename, "content": content})

            except UnicodeDecodeError:
                logger.error(f"Error decoding file {filename} as UTF-8.")
                excluded_files.append(filename)

        # Append file contents to the user message
        combined_message = user_message
        if file_contents:
            combined_message += (
                "\n\nPlease consider the following files in your response:\n"
            )
            for file in file_contents:
                combined_message += f"\n### File: {file['filename']}\n"
                combined_message += "```\n"
                combined_message += file["content"]
                combined_message += "\n```\n"

            combined_message += "\nPlease analyze the files above and provide your insights."

        # Check total tokens
        total_tokens = count_tokens(combined_message)
        if total_tokens > MAX_INPUT_TOKENS:
            combined_message = truncate_message(combined_message, MAX_INPUT_TOKENS)

        # Retrieve the conversation history
        history = conversation_manager.get_context(chat_id)
        # Append the new user message with uploaded file contents
        history.append({"role": "user", "content": combined_message})

        # Get the default or selected model
        selected_model_id = session.get("model_id")  # Modify as per your application logic
        model_id = selected_model_id or Model.get_default().id
        model = Model.get_by_id(model_id)

        logger.debug(f"Using model '{model.name}' with ID {model.id}")

        # Get response from Azure OpenAI
        model_response = get_azure_response(
            messages=history,
            deployment_name=model.deployment_name,
            selected_model_id=model.id,
            max_completion_tokens=model.max_completion_tokens,
        )

        logger.info("Response from the model: %s", model_response)

        # Add the user's message and model's response to the conversation history
        conversation_manager.add_message(chat_id, "user", user_message)
        conversation_manager.add_message(chat_id, "assistant", model_response)

        # Prepare response data
        response_data = {"response": model_response}
        if excluded_files:
            response_data["excluded_files"] = excluded_files

        return jsonify(response_data)

    except Exception as ex:
        logger.exception(
            "An unexpected error occurred while handling the chat message: %s", ex
        )
        return (
            jsonify({"error": "An unexpected error occurred. Please try again later."}),
            500,
        )
```

