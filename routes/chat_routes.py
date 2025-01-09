import logging
import os
from typing import Union, Tuple, Dict, List
import tiktoken
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
from models import Chat, Model
from token_utils import count_tokens

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
MAX_INPUT_TOKENS = 8192  # Max tokens allowed for input (user message + file content)
MAX_CONTEXT_TOKENS = 128000  # Max tokens allowed for the entire context window (messages in database)
MODEL_NAME = "gpt-4"  # Model name for tiktoken encoding

# Initialize tokenizer outside the route handlers
try:
    encoding = tiktoken.encoding_for_model(MODEL_NAME)
except KeyError:
    logger.warning(f"Model '{MODEL_NAME}' not found. Falling back to 'cl100k_base' encoding.")
    encoding = tiktoken.get_encoding("cl100k_base")

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

def generate_chat_title(conversation_text: str) -> str:
    """Generate a chat title based on the first 5 messages."""
    # Extract key topics from the conversation
    lines = conversation_text.split("\n")
    user_messages = []
    for line in lines:
        if line.startswith("user:") and ": " in line:
            parts = line.split(": ", 1)
            if len(parts) == 2:
                user_messages.append(parts[1])

    if not user_messages:
        return "New Chat"

    # Combine first 3 user messages to find common themes
    combined = " ".join(user_messages[:3])
    words = [word.lower() for word in combined.split() if len(word) > 3]

    # Count word frequencies and get top 2 most common
    word_counts = {}
    for word in words:
        word_counts[word] = word_counts.get(word, 0) + 1
    top_words = sorted(word_counts, key=word_counts.get, reverse=True)[:2]

    # Create title from top words or fallback to default
    if top_words:
        return " ".join([word.capitalize() for word in top_words])
    return "New Chat"

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
    logger.debug(f"Received request to delete chat_id: {chat_id}")
    if not Chat.is_chat_owned_by_user(chat_id, current_user.id):
        logger.warning("Unauthorized delete attempt for chat %s by user %s", chat_id, current_user.id)
        return jsonify({"error": "Chat not found or access denied"}), 403

    try:
        Chat.delete(chat_id)
        logger.info("Chat %s deleted successfully", chat_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {e}")
        return jsonify({"error": "Failed to delete chat"}), 500

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

@bp.route("/update_chat_title/<chat_id>", methods=["POST"])
@login_required
def update_chat_title(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Update the title of a chat."""
    logger.debug(f"Received request to update title for chat_id: {chat_id}")
    if not Chat.is_chat_owned_by_user(chat_id, current_user.id):
        return jsonify({"error": "Chat not found or access denied"}), 403

    data = request.get_json()
    new_title = data.get("title")
    if not new_title:
        return jsonify({"error": "Title is required"}), 400

    try:
        Chat.update_title(chat_id, new_title)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating chat title: {e}")
        return jsonify({"error": "Failed to update chat title"}), 500

@bp.route("/chat", methods=["POST"])
@login_required
def handle_chat() -> Union[Response, Tuple[Response, int]]:
    """Handle incoming chat messages and return AI responses."""
    logger.debug("Received chat message")

    chat_id = session.get("chat_id")
    if not chat_id:
        logger.error("Chat ID not found in session.")
        return jsonify({"error": "Chat ID not found."}), 400

    # Fetch the model associated with the chat
    model_obj = Chat.get_model(chat_id)
    if model_obj is None:
        logger.error(f"No model associated with chat ID {chat_id}.")
        return jsonify({"error": "No model associated with this chat."}), 400

    if not model_obj.deployment_name:
        logger.error("Invalid model configuration: deployment name is missing.")
        return jsonify({"error": "Invalid model configuration. Please select a valid model."}), 400

    if not model_obj.api_key or not model_obj.api_endpoint:
        logger.error("Invalid model configuration: API key or endpoint is missing.")
        return jsonify({"error": "Invalid model configuration. Please check the API settings."}), 400

    # Sanitize user input before processing
    user_message = bleach.clean(request.form.get("message", "").strip())

    # Handle file uploads
    uploaded_files = request.files.getlist("files[]")
    included_files: List[Dict[str, str]] = []
    excluded_files: List[Dict[str, str]] = []
    file_contents: List[str] = []

    total_tokens = count_tokens(user_message, MODEL_NAME) if user_message else 0

    for file in uploaded_files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            mime_type = file.mimetype

            # Check MIME type
            if mime_type not in ALLOWED_MIME_TYPES:
                error_message = f"File type ({mime_type}) not allowed: {filename}"
                logger.warning(error_message)
                excluded_files.append({"filename": filename, "error": error_message})
                continue

            # Check file size
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)
            if file_length > MAX_FILE_SIZE:
                error_message = f"File too large: {filename} exceeds the {MAX_FILE_SIZE} byte limit."
                logger.warning(error_message)
                excluded_files.append({"filename": filename, "error": error_message})
                continue

            # Save the file
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(file_path)
                included_files.append({"filename": filename})

                # Read text-based file content
                if mime_type.startswith('text/'):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                    except Exception as e:
                        error_message = f"Error reading file {filename}: {e}"
                        logger.error(error_message)
                        excluded_files.append({"filename": filename, "error": error_message})
                        continue

                    # Truncate file content if it exceeds the token limit
                    truncated_content = truncate_message(file_content, MAX_FILE_CONTENT_LENGTH)
                    formatted_content = f"\nFile '{filename}' content:\n```\n{truncated_content}\n```\n"

                    # Check if adding the file content would exceed the total token limit
                    content_tokens = count_tokens(formatted_content, MODEL_NAME)
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
            if file.filename:
                error_message = f"File type not allowed or file is empty: {file.filename}"
            else:
                error_message = "Empty file received."

            logger.warning(error_message)
            excluded_files.append({"filename": file.filename or "Unknown", "error": error_message})

    # Combine user message and file contents
    if file_contents:
        combined_message = user_message + "\n" + "".join(file_contents) if user_message else "".join(file_contents)
    else:
        combined_message = user_message

    # Update chat title after 5 messages if it's still the default
    if combined_message and Chat.is_title_default(chat_id):
        messages = conversation_manager.get_context(chat_id)
        if len(messages) >= 5:
            # Generate title from first 5 messages
            conversation_text = "\n".join(
                f"{msg['role']}: {msg['content']}" 
                for msg in messages[:5]
            )
            new_title = generate_chat_title(conversation_text)
            Chat.update_title(chat_id, new_title)

    # Add the combined message to the conversation history
    if combined_message:
        conversation_manager.add_message(chat_id, "user", combined_message)

    # Prepare the messages for the API call, excluding system messages if required
    history = conversation_manager.get_context(
        chat_id,
        include_system=not model_obj.requires_o1_handling
    )

    # Get the response from Azure OpenAI
    try:
        model_config = {
            "messages": history,
            "deployment_name": model_obj.deployment_name,
            "max_completion_tokens": model_obj.max_completion_tokens,
            "api_endpoint": model_obj.api_endpoint,
            "api_key": model_obj.api_key,
            "api_version": model_obj.api_version,
            "requires_o1_handling": model_obj.requires_o1_handling,
        }

        timeout_seconds = 30
        start_time = datetime.now()

        model_response = get_azure_response(**model_config)

        # Check for timeout
        elapsed_time = (datetime.now() - start_time).total_seconds()
        if elapsed_time > timeout_seconds:
            logger.warning(f"Response took too long: {elapsed_time} seconds")
            return jsonify({"error": "The assistant is taking longer than usual to respond. Please try again."}), 504
        
        # Add the assistant's response to the conversation history
        conversation_manager.add_message(chat_id, "assistant", model_response)

        # Prepare the response data
        response_data = {"response": model_response}
        if included_files:
            response_data["included_files"] = included_files
        if excluded_files:
            response_data["excluded_files"] = excluded_files

        return jsonify(response_data)

    except Exception as ex:
        logger.exception("Error during chat handling: %s", ex)
        return jsonify({"error": "An unexpected error occurred."}), 500
