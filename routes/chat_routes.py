from flask import (
    Blueprint,
    request,
    jsonify,
    redirect,
    url_for,
    render_template,
    session,
)
from flask.wrappers import Response
from flask_login import login_required, current_user
from typing import Union, Tuple, List, Dict, Any, Optional, cast
import os
from datetime import datetime, timedelta
import logging
import bleach
from models.model import Model
from conversation_manager import conversation_manager
from chat_utils import (
    allowed_file,
    generate_chat_title,
    generate_new_chat_id,
    process_file,
)
from chat_api import get_azure_response, scrape_data
from models.chat import Chat
import tiktoken
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Configure logging
logger = logging.getLogger(__name__)

# File Constants
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10 MB per file
MAX_TOTAL_FILE_SIZE = int(os.getenv("MAX_TOTAL_FILE_SIZE", 50 * 1024 * 1024))  # 50 MB
MAX_FILE_CONTENT_LENGTH = int(os.getenv("MAX_FILE_CONTENT_LENGTH", 8000))  # Characters

# Token Constants
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", 8192))  # Max input tokens
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", 128000))  # Max context tokens
DEFAULT_MODEL = "gpt-4"  # Default model name for tiktoken encoding

# Rate Limiting Constants
SCRAPE_RATE_LIMIT = "5 per minute"
CHAT_RATE_LIMIT = "60 per minute"

# Blueprint setup
chat_routes = Blueprint("chat", __name__)
limiter = Limiter(key_func=get_remote_address)

# Initialize tokenizer
try:
    encoding = tiktoken.encoding_for_model(DEFAULT_MODEL)
except KeyError:
    logger.warning(
        f"Model '{DEFAULT_MODEL}' not found. Falling back to 'cl100k_base' encoding."
    )
    encoding = tiktoken.get_encoding("cl100k_base")


def init_upload_folder() -> None:
    """Initialize the secure upload folder."""
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)


# Initialize upload folder
init_upload_folder()


def validate_chat_access(chat_id: str) -> bool:
    """Validate user's access to a chat.

    Args:
        chat_id: The ID of the chat to validate access for

    Returns:
        bool: True if user has access, False otherwise
    """
    return Chat.can_access_chat(chat_id, current_user.id, current_user.role)


def process_uploaded_files(files: List[Any]) -> Tuple[List[Dict], List[Dict], List[str], int]:
    """Process uploaded files and return processed data.

    Args:
        files: List of uploaded files

    Returns:
        Tuple containing included files, excluded files, file contents, and total tokens
    """
    included_files, excluded_files, file_contents = [], [], []
    total_tokens = 0

    for file in files:
        if not file or not file.filename:
            continue

        if not allowed_file(file.filename):
            excluded_files.append({
                "filename": file.filename or "Unknown",
                "error": "Invalid file type"
            })
            continue

        try:
            filename, content, tokens = process_file(file)
            if total_tokens + tokens > MAX_INPUT_TOKENS:
                excluded_files.append({
                    "filename": filename,
                    "error": "Exceeds token limit"
                })
                continue

            included_files.append({"filename": filename})
            file_contents.append(content)
            total_tokens += tokens

        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            excluded_files.append({
                "filename": file.filename,
                "error": str(e)
            })

    return included_files, excluded_files, file_contents, total_tokens


@chat_routes.route("/")
@login_required
def index() -> Response:
    """Redirect to the chat interface."""
    return cast(Response, redirect(url_for("chat.chat_interface")))


@chat_routes.route("/new_chat", methods=["GET", "POST"])
@login_required
def new_chat_route() -> Union[Response, Tuple[Response, int]]:
    """Create a new chat and return success JSON."""
    logger.debug(f"New chat request from user {current_user.id}")
    try:
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)

        Chat.create(chat_id=chat_id, user_id=user_id, title="New Chat")
        session["chat_id"] = chat_id
        logger.info("New chat created with ID: %s", chat_id)

        if request.method == "POST":
            return cast(Response, jsonify({"success": True, "chat_id": chat_id}))
        return cast(Response, render_template("new_chat.html"))
    except Exception as e:
        logger.error(f"Error creating new chat: {e}")
        return jsonify({"error": "Failed to create new chat"}), 500


@chat_routes.route("/chat_interface")
@login_required
def chat_interface() -> Response:
    """Render the main chat interface page."""
    logger.debug(f"Current user: id={current_user.id}, role={current_user.role}")

    chat_id = request.args.get("chat_id") or session.get("chat_id")

    if not chat_id or not Chat.get_by_id(chat_id):
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        Chat.create(chat_id=chat_id, user_id=user_id, title="New Chat")
        session["chat_id"] = chat_id
        logger.info(f"Created new chat {chat_id} for user {user_id}")
        if request.args.get("chat_id"):
            return cast(Response, redirect(url_for("chat.chat_interface")))

    chat = Chat.get_by_id(chat_id)
    if not chat:
        logger.error(f"Chat {chat_id} not found")
        return cast(Response, redirect(url_for("chat.chat_interface")))

    model = Model.get_by_id(chat.model_id) if chat.model_id else None
    chat_title = chat.title
    model_name = model.name if model else "Default Model"

    # Get messages and process them for display
    messages = conversation_manager.get_context(chat_id)
    for message in messages:
        if message['role'] == 'assistant':
            # Escape any Jinja2 template syntax in stored messages
            message['content'] = message['content'].replace("{%", "&#123;%").replace("%}", "%&#125;")

    models = Model.get_all()
    conversations = [
        {
            **conversation,
            "timestamp": datetime.strptime(
                str(conversation["timestamp"]), "%Y-%m-%d %H:%M:%S"
            ),
        }
        for conversation in Chat.get_user_chats(current_user.id)
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    return cast(Response, render_template(
        "chat.html",
        chat_id=chat_id,
        chat_title=chat_title,
        model_name=model_name,
        messages=messages,
        models=models,
        conversations=conversations,
        now=datetime.now,
        today=today,
        yesterday=yesterday,
    ))


@chat_routes.route("/get_chat_context/<chat_id>")
@login_required
def get_chat_context(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Get the conversation context for a chat."""
    if not validate_chat_access(chat_id):
        logger.warning("Unauthorized access attempt to chat %s", chat_id)
        return jsonify({"error": "Chat not found or access denied"}), 403

    messages = conversation_manager.get_context(chat_id)
    # Process messages to escape Jinja2 template syntax
    for message in messages:
        if message['role'] == 'assistant':
            message['content'] = message['content'].replace("{%", "&#123;%").replace("%}", "%&#125;")
    return cast(Response, jsonify({"messages": messages}))


@chat_routes.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Delete a chat and its associated messages."""
    logger.debug(f"Received request to delete chat_id: {chat_id}")
    if not validate_chat_access(chat_id):
        logger.warning(
            "Unauthorized delete attempt for chat %s by user %s",
            chat_id,
            current_user.id,
        )
        return jsonify({"error": "Chat not found or access denied"}), 403

    try:
        Chat.soft_delete(chat_id)
        logger.info("Chat %s deleted successfully", chat_id)
        return cast(Response, jsonify({"success": True}))
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {e}")
        return jsonify({"error": "Failed to delete chat"}), 500


@chat_routes.route("/scrape", methods=["POST"])
@login_required
@limiter.limit(SCRAPE_RATE_LIMIT)
def scrape() -> Union[Response, Tuple[Response, int]]:
    """Handle web scraping requests."""
    data = request.get_json()
    query = bleach.clean(data.get("query", "").strip())
    if not query:
        return jsonify({"error": "Query is required."}), 400

    try:
        response = scrape_data(query)
        return cast(Response, jsonify({"response": response}))
    except ValueError as ex:
        logger.error("ValueError during scraping: %s", ex)
        return jsonify({"error": str(ex)}), 400
    except Exception as ex:
        logger.error("Error during scraping: %s", str(ex))
        return jsonify({"error": "An error occurred during scraping"}), 500


@chat_routes.route("/update_chat_title/<chat_id>", methods=["POST"])
@login_required
def update_chat_title(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Update the title of a chat."""
    logger.debug(f"Received request to update title for chat_id: {chat_id}")
    if not validate_chat_access(chat_id):
        return jsonify({"error": "Chat not found or access denied"}), 403

    data = request.get_json()
    title = bleach.clean(data.get("title", "").strip())
    if not title or len(title) > 100:
        return (
            jsonify({"error": "Title is required and must be under 100 characters"}),
            400,
        )

    try:
        Chat.update_title(chat_id, title)
        return cast(Response, jsonify({"success": True}))
    except Exception as e:
        logger.error(f"Error updating chat title: {e}")
        return jsonify({"error": "Failed to update chat title"}), 500


def validate_model(model_obj: Optional[Model]) -> Optional[str]:
    """Validate model configuration.

    Args:
        model_obj: Model object to validate

    Returns:
        Optional[str]: Error message if validation fails, None if successful
    """
    if model_obj is None:
        return "No model associated with this chat."

    if not all([
        getattr(model_obj, 'deployment_name', None),
        getattr(model_obj, 'api_key', None),
        getattr(model_obj, 'api_endpoint', None)
    ]):
        return "Invalid model configuration. Please check the settings."

    return None


@chat_routes.route("/stats/<chat_id>", methods=["GET"])
@login_required
def get_chat_stats(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Get chat usage statistics."""
    try:
        if not validate_chat_access(chat_id):
            return jsonify({"error": "Unauthorized access to chat"}), 403

        stats = conversation_manager.get_usage_stats(chat_id)
        return cast(Response, jsonify({
            "success": True,
            "stats": stats
        }))
    except Exception as e:
        logger.error(f"Error getting chat stats: {e}")
        return jsonify({"error": "Failed to get chat statistics"}), 500


@chat_routes.route("/", methods=["POST"])
@login_required
@limiter.limit(CHAT_RATE_LIMIT)
def handle_chat() -> Union[Response, Tuple[Response, int]]:
    """Handle incoming chat messages and return AI responses."""
    try:
        chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id")
        if not chat_id:
            return jsonify({"error": "Chat ID not found."}), 400

        if not validate_chat_access(chat_id):
            return jsonify({"error": "Unauthorized access to chat"}), 403

        model_obj = Chat.get_model(chat_id)
        model_error = validate_model(model_obj)
        if model_error:
            return jsonify({"error": model_error}), 400

        # Validate message is present in form data
        if "message" not in request.form:
            return jsonify({"error": "Message is required."}), 400

        user_message = bleach.clean(request.form.get("message", "").strip())
        if not user_message and not request.files:
            return jsonify({"error": "Message or files are required."}), 400

        logger.debug(f"User message: {user_message}")

        included_files, excluded_files, file_contents, total_tokens = process_uploaded_files(
            request.files.getlist("files[]")
        )

        combined_message = (
            (user_message + "\n" + "".join(file_contents))
            if file_contents
            else user_message
        )

        if Chat.is_title_default(chat_id) and len(conversation_manager.get_context(chat_id)) >= 5:
            conversation_text = "\n".join(
                f"{msg['role']}: {msg['content']}"
                for msg in conversation_manager.get_context(chat_id)[:5]
            )
            Chat.update_title(chat_id, generate_chat_title(conversation_text))

        # Add user message with metadata
        conversation_manager.add_message(
            chat_id=chat_id,
            role="user",
            content=combined_message,
            model_max_tokens=getattr(model_obj, 'max_tokens', None),
            requires_o1_handling=getattr(model_obj, 'requires_o1_handling', False)
        )

        # Get optimized context
        history = conversation_manager.get_context(
            chat_id,
            include_system=not getattr(model_obj, 'requires_o1_handling', False)
        )

        # Get Azure response
        logger.debug("Sending request to Azure API")
        model_response = get_azure_response(
            messages=history,
            deployment_name=getattr(model_obj, 'deployment_name', ''),
            max_completion_tokens=getattr(model_obj, 'max_completion_tokens', 0),
            api_endpoint=getattr(model_obj, 'api_endpoint', ''),
            api_key=getattr(model_obj, 'api_key', ''),
            api_version=getattr(model_obj, 'api_version', ''),
            requires_o1_handling=getattr(model_obj, 'requires_o1_handling', False),
            timeout_seconds=120,
        )
        logger.debug("Received API response: %d chars", len(model_response))

        # Process model response to escape any Jinja2 template syntax
        processed_response = model_response.replace("{%", "&#123;%").replace("%}", "%&#125;")

        # Add assistant response with metadata
        conversation_manager.add_message(
            chat_id=chat_id,
            role="assistant",
            content=processed_response,
            model_max_tokens=getattr(model_obj, 'max_tokens', None),
            requires_o1_handling=getattr(model_obj, 'requires_o1_handling', False)
        )

        return cast(Response, jsonify({
            "response": processed_response,
            "included_files": included_files,
            "excluded_files": excluded_files,
        }))

    except Exception as ex:
        logger.error("Error during chat handling: %s", str(ex), exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500
