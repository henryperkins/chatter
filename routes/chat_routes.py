from flask import (
    Blueprint,
    request,
    jsonify,
    redirect,
    url_for,
    render_template,
    session,
    Response,
)
from flask_login import login_required, current_user
from typing import Union, Tuple
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
from extensions import csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Configure logging
logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10 MB per file
MAX_TOTAL_FILE_SIZE = int(os.getenv("MAX_TOTAL_FILE_SIZE", 50 * 1024 * 1024))  # 50 MB
MAX_FILE_CONTENT_LENGTH = int(os.getenv("MAX_FILE_CONTENT_LENGTH", 8000))  # Characters
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", 8192))  # Max input tokens
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", 128000))  # Max context tokens
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")  # Model name for tiktoken encoding

# Initialize tokenizer
try:
    encoding = tiktoken.encoding_for_model(MODEL_NAME)
except KeyError:
    logger.warning(
        f"Model '{MODEL_NAME}' not found. Falling back to 'cl100k_base' encoding."
    )
    encoding = tiktoken.get_encoding("cl100k_base")

# Blueprint setup
chat_routes = Blueprint("chat", __name__)
limiter = Limiter(key_func=get_remote_address)

# Secure upload folder
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@chat_routes.route("/")
@login_required
def index() -> Response:
    """Redirect to the chat interface."""
    return redirect(url_for("chat.chat_interface"))


@chat_routes.route("/new_chat", methods=["GET", "POST"])
@login_required
def new_chat_route() -> Union[Response, Tuple[Response, int]]:
    """Create a new chat and return success JSON."""
    logger.debug(f"New chat request from user {current_user.id}")
    try:
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)

        Chat.create(chat_id, user_id, "New Chat")
        session["chat_id"] = chat_id
        logger.info("New chat created with ID: %s", chat_id)

        if request.method == "POST":
            return jsonify({"success": True, "chat_id": chat_id})
        return render_template("new_chat.html")
    except Exception as e:
        logger.error(f"Error creating new chat: {e}")
        return jsonify({"error": "Failed to create new chat"}), 500


@chat_routes.route("/chat_interface")
@login_required
def chat_interface() -> str:
    """Render the main chat interface page."""
    logger.debug(f"Current user: id={current_user.id}, role={current_user.role}")

    # Get chat_id from query params or session
    chat_id = request.args.get("chat_id") or session.get("chat_id")

    # If chat doesn't exist or can't be accessed, create new chat
    if not chat_id or not Chat.get_by_id(chat_id):
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        Chat.create(chat_id, user_id, "New Chat")
        session["chat_id"] = chat_id
        logger.info(f"Created new chat {chat_id} for user {user_id}")
        # Redirect to remove stale chat_id from URL
        if request.args.get("chat_id"):
            return redirect(url_for("chat.chat_interface"))

    # Fetch chat data
    chat = Chat.get_by_id(chat_id)
    model = Model.get_by_id(chat.model_id) if chat.model_id else None
    chat_title = chat.title
    model_name = model.name if model else "Default Model"

    messages = conversation_manager.get_context(chat_id)
    models = Model.get_all()
    conversations = [
        {
            **conversation,
            "timestamp": datetime.strptime(
                conversation["timestamp"], "%Y-%m-%d %H:%M:%S"
            ),
        }
        for conversation in Chat.get_user_chats(current_user.id)
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    return render_template(
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
    )


@chat_routes.route("/get_chat_context/<chat_id>")
@login_required
def get_chat_context(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Get the conversation context for a chat."""
    if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
        logger.warning("Unauthorized access attempt to chat %s", chat_id)
        return jsonify({"error": "Chat not found or access denied"}), 403

    messages = conversation_manager.get_context(chat_id)
    return jsonify({"messages": messages})


@chat_routes.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
@csrf.exempt
def delete_chat(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Delete a chat and its associated messages."""
    logger.debug(f"Received request to delete chat_id: {chat_id}")
    if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
        logger.warning(
            "Unauthorized delete attempt for chat %s by user %s",
            chat_id,
            current_user.id,
        )
        return jsonify({"error": "Chat not found or access denied"}), 403

    try:
        Chat.soft_delete(chat_id)  # Use soft-delete instead of hard delete
        logger.info("Chat %s deleted successfully", chat_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {e}")
        return jsonify({"error": "Failed to delete chat"}), 500


@chat_routes.route("/scrape", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
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


@chat_routes.route("/update_chat_title/<chat_id>", methods=["POST"])
@login_required
@csrf.exempt
def update_chat_title(chat_id: str) -> Union[Response, Tuple[Response, int]]:
    """Update the title of a chat."""
    logger.debug(f"Received request to update title for chat_id: {chat_id}")
    if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
        return jsonify({"error": "Chat not found or access denied"}), 403

    data = request.get_json()
    new_title = data.get("title")
    if not new_title or len(new_title) > 100:
        return (
            jsonify({"error": "Title is required and must be under 100 characters"}),
            400,
        )

    try:
        Chat.update_title(chat_id, new_title)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating chat title: {e}")
        return jsonify({"error": "Failed to update chat title"}), 500


@chat_routes.route("/", methods=["POST"])
@login_required
def handle_chat() -> Union[Response, Tuple[Response, int]]:
    """Handle incoming chat messages and return AI responses."""
    try:
        logger.debug(
            "Received chat message from user %s with data: %s",
            current_user.id,
            {
                "form": request.form.to_dict(),
                "files": (
                    [f.filename for f in request.files.getlist("files[]")]
                    if request.files
                    else []
                ),
                "headers": dict(request.headers),
            },
        )

        # Try to get chat_id from headers first, then session
        chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id")
        if not chat_id:
            logger.error(
                "Chat ID not found in headers or session for user %s", current_user.id
            )
            return jsonify({"error": "Chat ID not found."}), 400

        # Verify chat access
        if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
            logger.error(
                "User %s attempted to access unauthorized chat %s",
                current_user.id,
                chat_id,
            )
            return jsonify({"error": "Unauthorized access to chat"}), 403

        # Fetch the model associated with the chat
        model_obj = Chat.get_model(chat_id)
        if model_obj is None:
            logger.error(f"No model associated with chat ID {chat_id}.")
            return jsonify({"error": "No model associated with this chat."}), 400

        if (
            not model_obj.deployment_name
            or not model_obj.api_key
            or not model_obj.api_endpoint
        ):
            logger.error("Invalid model configuration.")
            return (
                jsonify(
                    {"error": "Invalid model configuration. Please check the settings."}
                ),
                400,
            )

        # Sanitize user input before processing
        user_message = bleach.clean(request.form.get("message", "").strip())
        logger.debug(f"User message: {user_message}")

        # Handle file uploads
        uploaded_files = request.files.getlist("files[]")
        included_files, excluded_files, file_contents, total_tokens = [], [], [], 0

        for file in uploaded_files:
            if file and allowed_file(file.filename):
                try:
                    filename, content, tokens = process_file(file)
                    if total_tokens + tokens > MAX_INPUT_TOKENS:
                        excluded_files.append(
                            {"filename": filename, "error": "Exceeds token limit"}
                        )
                        continue
                    included_files.append({"filename": filename})
                    file_contents.append(content)
                    total_tokens += tokens
                except Exception as e:
                    logger.error(f"Error processing file {file.filename}: {e}")
                    excluded_files.append({"filename": file.filename, "error": str(e)})
            else:
                excluded_files.append(
                    {
                        "filename": file.filename or "Unknown",
                        "error": "Invalid file type",
                    }
                )

        # Combine user message and file contents
        combined_message = (
            (user_message + "\n" + "".join(file_contents))
            if file_contents
            else user_message
        )

        # Update chat title if necessary
        if (
            Chat.is_title_default(chat_id)
            and len(conversation_manager.get_context(chat_id)) >= 5
        ):
            conversation_text = "\n".join(
                f"{msg['role']}: {msg['content']}"
                for msg in conversation_manager.get_context(chat_id)[:5]
            )
            Chat.update_title(chat_id, generate_chat_title(conversation_text))

        # Add the combined message to the conversation history
        conversation_manager.add_message(
            chat_id,
            "user",
            combined_message,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
        )

        # Prepare the messages for the API call
        history = conversation_manager.get_context(
            chat_id, include_system=not model_obj.requires_o1_handling
        )

        logger.debug("Sending request to Azure API")
        model_response = get_azure_response(
            messages=history,
            deployment_name=model_obj.deployment_name,
            max_completion_tokens=model_obj.max_completion_tokens,
            api_endpoint=model_obj.api_endpoint,
            api_key=model_obj.api_key,
            api_version=model_obj.api_version,
            requires_o1_handling=model_obj.requires_o1_handling,
            timeout_seconds=120,
        )
        logger.debug("Received API response: %d chars", len(model_response))

        logger.debug("Adding assistant response to conversation")
        conversation_manager.add_message(
            chat_id,
            "assistant",
            model_response,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
        )

        logger.debug("Returning successful response")
        return jsonify(
            {
                "response": model_response,
                "included_files": included_files,
                "excluded_files": excluded_files,
            }
        )
    except Exception as ex:
        logger.error("Error during chat handling: %s", str(ex), exc_info=True)
        logger.error(
            "Failed request details: %s",
            {
                "chat_id": chat_id,
                "model": model_obj.deployment_name if "model_obj" in locals() else None,
                "message_length": (
                    len(combined_message) if "combined_message" in locals() else 0
                ),
                "file_count": (
                    len(included_files) if "included_files" in locals() else 0
                ),
                "error": str(ex),
            },
        )
        return (
            jsonify({"error": "An unexpected error occurred.", "details": str(ex)}),
            500,
        )
