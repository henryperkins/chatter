import logging
import os
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
from datetime import datetime, timedelta

from chat_api import scrape_data, get_azure_response
from chat_utils import generate_new_chat_id
from conversation_manager import ConversationManager
from database import get_db
from sqlalchemy import text
from models import Chat, Model
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
MAX_FILE_CONTENT_LENGTH = 8000  # Characters (increased to accommodate larger files)
MAX_INPUT_TOKENS = 8192  # Azure OpenAI input token limit
MAX_OUTPUT_TOKENS = 16384  # Azure OpenAI output token limit
MAX_CONTEXT_TOKENS = 128000  # Azure OpenAI context window limit

# Initialize tokenizer
encoding = tiktoken.encoding_for_model("gpt-4")  # Or whichever model you're using


def allowed_file(filename: str) -> bool:
    """Check if the file has an allowed extension."""
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def truncate_message(message: str, max_tokens: int) -> str:
    """Truncates a message to a specified number of tokens using tiktoken."""
    tokens = encoding.encode(message)
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens]
        truncated_message = encoding.decode(truncated_tokens)
        truncated_message += "\n\n[Note: The input was too long and has been truncated.]"
        return truncated_message
    return message


@bp.route("/")
@login_required
def index() -> Response:
    """Redirect to the chat interface."""
    return redirect(url_for("chat.chat_interface"))


@bp.route("/new_chat", methods=["GET", "POST"])
@login_required
def new_chat_route() -> Union[Response, Tuple[Response, int]]:
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
    chat_id = request.args.get("chat_id") or session.get("chat_id")

    if chat_id:
        if not Chat.is_chat_owned_by_user(chat_id, current_user.id):
            logger.warning("Unauthorized access attempt to chat %s", chat_id)
            return "Chat not found or access denied", 403

        session["chat_id"] = chat_id
    else:
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        Chat.create(chat_id, user_id, "New Chat")
        session["chat_id"] = chat_id

    messages = conversation_manager.get_context(chat_id)
    models = Model.get_all()
    conversations = Chat.get_user_chats(current_user.id)

    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    return render_template(
        "chat.html",
        chat_id=chat_id,
        messages=messages,
        models=models,
        conversations=conversations,
        now=datetime.now,
        today=today,
        yesterday=yesterday,
    )


@bp.route("/load_chat/<chat_id>")
@login_required
def load_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Load and return the messages for a specific chat."""
    db = get_db()
    try:
        chat = db.query(Chat).filter(
            Chat.id == chat_id,
            Chat.user_id == current_user.id
        ).first()

        if not chat:
            logger.warning("Unauthorized access attempt to chat %s", chat_id)
            return jsonify({"error": "Chat not found or access denied"}), 403

        messages = conversation_manager.get_context(chat_id)
        messages_to_send = [msg for msg in messages if msg["role"] != "system"]
        return jsonify({"messages": messages_to_send})
    finally:
        db.close()


@bp.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Delete a chat and its associated messages."""
    db = get_db()
    try:
        chat_to_delete = db.query(Chat).filter(
            Chat.id == chat_id,
            Chat.user_id == current_user.id
        ).first()

        if not chat_to_delete:
            logger.warning(
                "Attempt to delete non-existent or unauthorized chat: %s", chat_id
            )
            return jsonify({"error": "Chat not found or access denied"}), 403

        try:
            db.execute(text("PRAGMA foreign_keys = ON"))
            db.delete(chat_to_delete)
            db.commit()
            logger.info("Chat %s deleted successfully", chat_id)
            return jsonify({"success": True})
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting chat {chat_id}: {e}")
            return jsonify({"error": "Failed to delete chat"}), 500
    finally:
        db.close()


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
        logger.error("Chat ID not found in session.")
        return jsonify({"error": "Chat ID not found."}), 400

    model_id = Chat.get_model(chat_id)
    model_obj = Model.get_by_id(model_id) if model_id else Model.get_default()
    requires_o1_handling = model_obj.requires_o1_handling if model_obj else False

    if not model_obj or not model_obj.deployment_name:
        logger.error("Invalid model configuration: deployment name is missing.")
        return jsonify({"error": "Invalid model configuration. Please select a valid model."}), 400

    if not model_obj.api_key or not model_obj.api_endpoint:
        logger.error("Invalid model configuration: API key or endpoint is missing.")
        return jsonify({"error": "Invalid model configuration. Please check the API settings."}), 400

    user_message = bleach.clean(request.form.get("message", "").strip())
    uploaded_files = request.files.getlist("files[]")
    included_files = []
    excluded_files = []
    file_contents = []
    total_tokens = len(encoding.encode(user_message)) if user_message else 0

    for file in uploaded_files:
        if file:
            filename = secure_filename(file.filename)
            mime_type = file.mimetype

            if not allowed_file(filename) or mime_type not in ALLOWED_MIME_TYPES:
                error_message = f"File type not allowed: {filename}"
                logger.warning(error_message)
                excluded_files.append({"filename": filename, "error": error_message})
                continue

            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)
            if file_length > MAX_FILE_SIZE:
                error_message = f"File too large: {filename} exceeds the 10MB limit."
                logger.warning(error_message)
                excluded_files.append({"filename": filename, "error": error_message})
                continue

            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(file_path)
                included_files.append({"filename": filename})
                if mime_type.startswith('text/'):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                    except Exception as e:
                        error_message = f"Error reading file {filename}: {e}"
                        logger.error(error_message)
                        excluded_files.append({"filename": filename, "error": error_message})
                        continue

                    truncated_content = truncate_message(file_content, MAX_FILE_CONTENT_LENGTH)
                    formatted_content = f"\nFile '{filename}' content:\n```\n{truncated_content}\n```\n"
                    
                    content_tokens = len(encoding.encode(formatted_content))
                    if total_tokens + content_tokens > MAX_INPUT_TOKENS:
                        error_message = f"File {filename} skipped: Adding it would exceed the {MAX_INPUT_TOKENS} token limit"
                        logger.warning(error_message)
                        excluded_files.append({"filename": filename, "error": error_message})
                        continue
                        
                    total_tokens += content_tokens
                    file_contents.append(formatted_content)
                else:
                    logger.info(f"Skipping reading content for non-text file: {filename}")
            except Exception as e:
                error_message = f"Error saving file {filename}: {e}"
                logger.error(error_message)
                excluded_files.append({"filename": filename, "error": error_message})
                continue
        else:
            error_message = "Empty file received."
            logger.warning(error_message)
            excluded_files.append({"filename": "Unknown", "error": error_message})

    if file_contents:
        combined_message = user_message + "\n" + "".join(file_contents) if user_message else "".join(file_contents)
    else:
        combined_message = user_message

    if combined_message:
        conversation_manager.add_message(chat_id, "user", combined_message)

        if user_message and Chat.is_title_default(chat_id):
            new_title = user_message.split("\n")[0][:50]
            Chat.update_title(chat_id, new_title)

    history = conversation_manager.get_context(
        chat_id,
        include_system=not requires_o1_handling
    )

    try:
        model_config = {
            "messages": history,
            "deployment_name": model_obj.deployment_name if model_obj else None,
            "selected_model_id": model_id,
            "max_completion_tokens": model_obj.max_completion_tokens if model_obj else MAX_OUTPUT_TOKENS,
            "api_endpoint": model_obj.api_endpoint if model_obj else None,
            "api_key": model_obj.api_key if model_obj else None,
            "api_version": model_obj.api_version if model_obj else None,
            "requires_o1_handling": model_obj.requires_o1_handling if model_obj else False,
        }

        timeout_seconds = 30
        start_time = datetime.now()

        model_response = get_azure_response(**model_config)

        elapsed_time = (datetime.now() - start_time).total_seconds()
        if elapsed_time > timeout_seconds:
            logger.warning(f"Response took too long: {elapsed_time} seconds")
            return jsonify({"error": "The assistant is taking longer than usual to respond. Please try again."}), 504

        conversation_manager.add_message(chat_id, "assistant", model_response)

        response_data = {"response": model_response}
        if included_files:
            response_data["included_files"] = included_files
        if excluded_files:
            response_data["excluded_files"] = excluded_files

        return jsonify(response_data)

    except Exception as ex:
        logger.exception("Error during chat handling: %s", ex)
        return jsonify({"error": "An unexpected error occurred."}), 500
