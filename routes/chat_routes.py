""" 
Module for handling chat routes.

This module provides routes for managing chat interactions, including:
- Chat interface pages
- Message handling
- Chat session management
- Stats and utility routes
"""

import os
import uuid
import json
import bleach
import tiktoken
import mistune
from datetime import datetime, timedelta
from typing import Union, Tuple, Dict, Any, Optional, cast, List, Generator

from flask import (
    Response,
    Blueprint,
    request,
    jsonify,
    redirect,
    url_for,
    render_template,
    session,
    make_response,
)
from flask.wrappers import Response as FlaskResponse
from flask_login import login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import generate_csrf
from sqlalchemy import text
from extensions import csrf

# ----------------------------------------------------------------------------
# Updated Import: Use relative import for scrape_data
# ----------------------------------------------------------------------------
from chat_api import get_azure_response, scrape_data
from azure_search_client import AzureOpenAI
from chat_utils import generate_new_chat_id, process_uploaded_files
from conversation_manager import conversation_manager
from database import db_session
from models.chat import Chat
from models.model import Model
from models.provider import Provider

from config import config_instance

# Centralized logging
from logging_config import get_logger
logger = get_logger(__name__)

# ----------------------------------------------------------------------------
# File Constants
# ----------------------------------------------------------------------------
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", default=str(10 * 1024 * 1024)))  # 10 MB
MAX_TOTAL_FILE_SIZE = int(os.getenv("MAX_TOTAL_FILE_SIZE", default=str(50 * 1024 * 1024)))  # 50 MB
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx", "md"}

# ----------------------------------------------------------------------------
# Token & Model Constants
# ----------------------------------------------------------------------------
DEFAULT_MODEL = "gpt-4"
MODEL_NAME = DEFAULT_MODEL
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", default="8192"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", default="128000"))

# ----------------------------------------------------------------------------
# Rate Limiting Constants
# ----------------------------------------------------------------------------
SCRAPE_RATE_LIMIT = "5 per minute"
CHAT_RATE_LIMIT = "60 per minute"

# ----------------------------------------------------------------------------
# Blueprint and Limiter
# ----------------------------------------------------------------------------
chat_routes = Blueprint("chat", __name__, url_prefix="/chat")
limiter = Limiter(key_func=get_remote_address)

# ----------------------------------------------------------------------------
# Token Encoding Initialization with Fallback
# ----------------------------------------------------------------------------
def get_token_encoder(model_name: str = DEFAULT_MODEL):
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        logger.warning("Model '%s' not found. Using 'cl100k_base'.", model_name)
        return tiktoken.get_encoding("cl100k_base")


encoding = get_token_encoder()

# ----------------------------------------------------------------------------
# Upload Folder Initialization
# ----------------------------------------------------------------------------
def init_upload_folder() -> None:
    """Initialize the secure upload folder if it doesn't exist."""
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)

init_upload_folder()

# ----------------------------------------------------------------------------
# Server-side Markdown Rendering
# ----------------------------------------------------------------------------
def server_side_format_markdown(raw_text: str) -> str:
    """
    Convert raw text to HTML using Mistune server-side rendering.
    """
    markdown_processor = mistune.create_markdown(plugins=["url", "table"], escape=False)
    return markdown_processor(raw_text)

##############################################################################
# Validation / Helper Functions
##############################################################################
def validate_chat_access(chat_id: Optional[str]) -> bool:
    """
    Check if the current user can access the given chat.
    """
    if not chat_id or not isinstance(chat_id, str):
        return False
    return Chat.can_access_chat(chat_id, current_user.id, current_user.role)


def validate_model(model: Optional[Model]) -> Optional[str]:
    """
    Validate a model's configuration.
    Returns None if valid; otherwise returns an error message.
    """
    if not model:
        return "No model configured for this chat."

    try:
        # Type-safe access to model attributes
        max_completion_tokens = getattr(model, "max_completion_tokens", None)
        if max_completion_tokens is None:
            return "max_completion_tokens is required"

        try:
            max_completion_tokens = int(max_completion_tokens)
            if not (1 <= max_completion_tokens <= 16384):
                return "max_completion_tokens must be between 1 and 16384"
        except (TypeError, ValueError):
            return "max_completion_tokens must be a valid integer"

        # Type-safe provider access
        provider_id = getattr(model, "provider_id", None)
        provider = Provider.get_by_id(provider_id) if provider_id else None
        if not provider:
            return "Invalid provider configuration"

        provider_max = provider.capabilities.get("max_tokens", 16384)
        model_type = getattr(model, "model_type", "")
        if not model_type:
            return "model_type is required"

        requires_o1 = getattr(model, "requires_o1_handling", False)
        is_o1_preview = model_type.lower() == "o1-preview" and requires_o1

        if is_o1_preview and max_completion_tokens > 8300:
            return "o1-preview models are limited to 8300 max_completion_tokens"

        return None

    except Exception as e:
        logger.error("Model validation error: %s", str(e))
        return f"Invalid model configuration: {str(e)}"


def get_model_token_limit(model_obj: Any) -> int:
    """
    Safely retrieve the model's max_tokens, or fallback to 16384.
    """
    max_tokens = getattr(model_obj, "max_tokens", None)
    if isinstance(max_tokens, int) and max_tokens > 0:
        return max_tokens
    return 16384


def truncate_content(text: str, max_tokens: int, truncation_note: str) -> str:
    """
    Truncate the given text to `max_tokens` and append a note if truncated.
    """
    try:
        tok = get_token_encoder(DEFAULT_MODEL)
    except KeyError:
        logger.warning("Model '%s' not found. Using 'cl100k_base'.", DEFAULT_MODEL)
        tok = tiktoken.get_encoding("cl100k_base")

    tokens = tok.encode(text)
    note_tokens = tok.encode(truncation_note)
    allowed = max_tokens - len(note_tokens)
    truncated_tokens = tokens[:allowed]
    truncated_text = tok.decode(truncated_tokens)
    return truncated_text + truncation_note


def validate_chat_request(request_data) -> Dict[str, Any]:
    """
    Validate incoming chat request (e.g. CSRF token, chat_id).
    Return a dict with {"valid": bool, "error": str, "chat_id": str}.
    """
    try:
        if not request_data.form:
            return {"valid": False, "error": "Missing form data"}

        chat_id = request_data.headers.get("X-Chat-ID") or session.get("chat_id")
        if not chat_id:
            return {"valid": False, "error": "Chat ID not found"}

        if not validate_chat_access(chat_id):
            return {"valid": False, "error": "Unauthorized access to chat"}

        return {"valid": True, "chat_id": chat_id}

    except Exception as e:
        logger.error("Request validation error: %s", str(e), exc_info=True)
        return {"valid": False, "error": "Request validation failed"}

##############################################################################
# 1) Chat Interface Pages
##############################################################################
@chat_routes.route("/interface")
@login_required
def index() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    GET /chat/interface
    Checks for models, creates new chat if needed, retrieves conversation history,
    and renders chat.html.
    """
    try:
        with db_session() as db:
            try:
                model_count = db.execute(text("SELECT COUNT(*) FROM models")).scalar()
                if model_count == 0:
                    logger.warning("No models found - showing error message")
                    rendered = render_template(
                        "error.html",
                        error=(
                            "No AI models are configured. Please contact your administrator "
                            "or create a new model in the Models section."
                        ),
                        show_models_link=True,
                    )
                    response = make_response(rendered)
                    response.status_code = 200  # or 500 if you'd prefer a server error
                    return response

                # Instead of always creating a new chat, reuse session chat_id if valid
                temp_chat_id = session.get("chat_id", "")
                if not isinstance(temp_chat_id, str):
                    temp_chat_id = str(temp_chat_id)
                chat_id = temp_chat_id

                existing_chat = Chat.get_by_id(str(chat_id)) if chat_id else None

                # Edge cases:
                # - No chat_id in session
                # - The session's chat_id is invalid or points to a deleted chat
                # In either scenario, create a new chat only once:
                if not existing_chat:
                    new_id = generate_new_chat_id()
                    Chat.create(chat_id=new_id, user_id=current_user.id, title="New Chat")
                    session["chat_id"] = new_id
                    chat_id = new_id

                chat = Chat.get_by_id(str(chat_id))
                if chat:
                    model_obj = Chat.get_model(str(chat_id)) if chat.model_id else Model.get_default()
                    if not model_obj:
                        model_obj = Model.get_default()
                        if model_obj:
                            chat.model_id = model_obj.id
                            Chat.update_model_id(str(chat_id), model_obj.id)
                else:
                    model_obj = None
                    # Ensure session is marked modified after creating new chat
                    session.modified = True
            except Exception as e:
                logger.error("Error creating chat: %s", str(e))
                error_json = jsonify({"error": "Internal server error"})
                error_json.status_code = 500
                return error_json
    except Exception as e:
        logger.error("Database error: %s", str(e))
        error_json = jsonify({"error": "Database error"})
        error_json.status_code = 500
        return error_json

    try:
        chat_title = chat.title if chat else "New Chat"
        model_name = model_obj.name if model_obj else "Default Model"
        current_model = model_obj

        # Get Azure token if available
        azure_token = None
        if current_model and current_model.api_key:
            try:
                from utils.encryption import decrypt_api_key, EncryptionError
                if current_model.api_key:
                    try:
                        azure_token = decrypt_api_key(
                            current_model.api_key,
                            config_instance.ENCRYPTION_KEY,
                        )
                    except EncryptionError as e:
                        logger.error("Error decrypting Azure token: %s", str(e))
                        rendered = render_template(
                            "error.html",
                            error="Configuration error: Unable to decrypt API key. Please contact your administrator."
                        )
                        response = make_response(rendered)
                        response.status_code = 500
                        return response
                else:
                    azure_token = None
                    logger.warning("No API key found for model.")
            except Exception as e:
                logger.error("Error decrypting Azure token: %s", str(e))

        # Retrieve the conversation history and sanitize user messages
        messages = conversation_manager.get_context(chat_id)
        for message in messages:
            if message["role"] == "user":
                message["content"] = bleach.clean(message["content"])

        rendered = render_template(
            "chat.html",
            chat_id=chat_id,
            chat_title=chat_title,
            model_name=model_name,
            current_model=current_model,
            messages=messages,  # Updated to pass the conversation history
            models=Model.get_all(),
            conversations=Chat.get_user_chats(current_user.id),
            now=datetime.now,
            today=datetime.now().strftime("%Y-%m-%d"),
            yesterday=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            azure_token=azure_token,
        )
        response = make_response(rendered)
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("Error initializing chat interface: %s", str(e))
        error_json = jsonify({"error": "Internal server error"})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/chat_interface", methods=["GET"])
@login_required
def chat_interface() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    GET /chat/chat_interface
    Renders chat.html for an existing or new chat ID, plus existing messages.
    """
    logger.debug("Current user: id=%s, role=%s", current_user.id, current_user.role)

    temp_chat_id = request.args.get("chat_id") or session.get("chat_id", "")
    if not isinstance(temp_chat_id, str):
        temp_chat_id = str(temp_chat_id)
    chat_id = temp_chat_id

    if request.args.get("chat_id"):
        session["chat_id"] = chat_id

    # Ensure we have a valid chat_id
    if not chat_id:
        chat_id = generate_new_chat_id()
        Chat.create(chat_id=chat_id, user_id=current_user.id, title="New Chat")
        session["chat_id"] = chat_id

    # If no chat_id or the chat doesn't exist, create new
    if not chat_id or not Chat.get_by_id(chat_id):
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        try:
            with db_session() as db:
                model_count = db.execute(text("SELECT COUNT(*) FROM models")).scalar()
                if model_count == 0:
                    rendered = render_template(
                        "error.html",
                        error=(
                            "No AI models are configured. Please contact your administrator "
                            "or create a new model in the Models section."
                        ),
                        show_models_link=True,
                    )
                    response = make_response(rendered)
                    response.status_code = 200  # or 500, depending on your design
                    return response

            Chat.create(chat_id=chat_id, user_id=user_id, title="New Chat")
            session["chat_id"] = chat_id
            return redirect(url_for("chat.index"))
        except Exception as e:
            logger.error("Error creating chat: %s", e)
            rendered = render_template(
                "error.html",
                error="Could not initialize chat. Please contact an administrator.",
            )
            response = make_response(rendered)
            response.status_code = 500
            return response

    chat = Chat.get_by_id(chat_id)
    if not chat:
        logger.error("Chat %s not found", chat_id)
        return cast(FlaskResponse, redirect(url_for("chat.chat_interface")))

    try:
        model_obj = Chat.get_model(chat_id) if chat.model_id else None
        if not model_obj and chat.model_id:
            logger.error("Failed to retrieve model for chat %s.", chat_id)
            rendered = render_template(
                "error.html",
                error="The model configuration is invalid. Please contact an administrator.",
            )
            response = make_response(rendered)
            response.status_code = 500
            return response

        chat_title = chat.title
        model_name = model_obj.name if model_obj else "Default Model"

        azure_token = None
        if model_obj and model_obj.api_key:
            try:
                from utils.encryption import decrypt_api_key, EncryptionError
                if model_obj.api_key:
                    try:
                        azure_token = decrypt_api_key(
                            model_obj.api_key,
                            config_instance.ENCRYPTION_KEY,
                        )
                    except EncryptionError as e:
                        logger.error("Error decrypting Azure token: %s", str(e))
                        rendered = render_template(
                            "error.html",
                            error="Configuration error: Unable to decrypt API key. Please contact your administrator."
                        )
                        response = make_response(rendered)
                        response.status_code = 500
                        return response
                else:
                    azure_token = None
                    logger.warning("No API key found for model.")
            except Exception as e:
                logger.error("Error decrypting Azure token: %s", str(e))
        current_model = model_obj
    except Exception as e:
        logger.error("Error retrieving model for chat %s: %s", chat_id, str(e))
        rendered = render_template(
            "error.html",
            error="An error occurred while retrieving the model configuration.",
        )
        response = make_response(rendered)
        response.status_code = 500
        return response

    messages = conversation_manager.get_context(chat_id)
    if not messages:
        # Add both welcome message and helpful instructions
        conversation_manager.add_message(
            chat_id=chat_id,
            role="system",
            content="Welcome to Azure OpenAI Chat! Start by typing a message."
        )
        conversation_manager.add_message(
            chat_id=chat_id,
            role="assistant",
            content="Hello! I'm ready to help. You can:\n- Type a message to chat\n- Upload files for analysis\n- Change models using the dropdown\n- Start a new chat with the + button"
        )
        messages = conversation_manager.get_context(chat_id)

    for message in messages:
        if message["role"] == "user":
            message["content"] = bleach.clean(message["content"])

    models = Model.get_all()
    models_serialized = []
    for m in models:
        models_serialized.append({
            "id": m.id,
            "name": m.name,
            "is_default": m.is_default,
            "model_type": m.model_type,
            "requires_o1_handling": m.requires_o1_handling,
            "supports_streaming": m.supports_streaming,
            "max_completion_tokens": m.max_completion_tokens,
            "provider_id": m.provider_id,
            "api_version": m.api_version,
            "deployment_name": m.deployment_name,
            "description": m.description,
            "temperature": m.temperature,
            "max_tokens": m.max_tokens,
            "api_endpoint": m.api_endpoint,
        })

    conversations = Chat.get_user_chats(current_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    current_model_data = None
    if current_model:
        current_model_data = {
            "id": current_model.id,
            "name": current_model.name,
            "model_type": current_model.model_type,
            "requires_o1_handling": current_model.requires_o1_handling,
            "supports_streaming": current_model.supports_streaming,
            "max_completion_tokens": current_model.max_completion_tokens,
            "api_version": current_model.api_version,
            "deployment_name": current_model.deployment_name,
            "api_endpoint": current_model.api_endpoint,
        }

    # Ensure CHAT_CONFIG is properly initialized even for new chats
    chat_config = {
        "chatId": chat_id,
        "csrfToken": generate_csrf(),
        "azureToken": azure_token or "",
        "userId": str(current_user.id),
        "modelSettings": current_model_data or {}
    }

    rendered = render_template(
        "chat.html",
        chat_id=chat_id,
        chat_title=chat_title,
        model_name=model_name,
        current_model=current_model_data,
        messages=messages,
        models=models_serialized,
        conversations=conversations,
        now=datetime.now,
        today=today,
        yesterday=yesterday,
        azure_token=azure_token,
        CHAT_CONFIG=json.dumps(chat_config)
    )
    response = make_response(rendered)
    response.status_code = 200
    return response

##############################################################################
# 2) Create a New Chat
##############################################################################
@chat_routes.route("/new", methods=["POST"])
@login_required
def new_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Create a new chat session and return the new chat_id.
    """
    try:
        chat_id = str(uuid.uuid4())
        Chat.create(chat_id=chat_id, user_id=current_user.id, title="New Chat")
        return jsonify({"success": True, "chat_id": chat_id})
    except Exception as e:
        logger.error("Error creating new chat: %s", str(e), exc_info=True)
        error_json = jsonify({"error": str(e)})
        error_json.status_code = 500
        return error_json


@chat_routes.after_request
def add_cors_headers(response: FlaskResponse) -> FlaskResponse:
    """Add required CORS headers for streaming support."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Chat-ID, api-key, X-CSRFToken"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Accel-Buffering"] = "no"  # Disable buffering for nginx
    return response

##############################################################################
# 3) Send a Chat Message
##############################################################################
@chat_routes.route("/send", methods=["POST", "OPTIONS"])
@csrf.exempt
@login_required
@limiter.limit(CHAT_RATE_LIMIT)
def handle_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Handle chat messages with optional file uploads, returning streaming or normal.
    """
    # Handle preflight request
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, X-Chat-ID, api-key, X-CSRFToken")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response

    # For POST requests, require login
    if not current_user.is_authenticated:
        error_json = jsonify({"error": "Authentication required"})
        error_json.status_code = 401
        return error_json

    try:
        logger.info("handle_chat: Content-Type = %s", request.headers.get('Content-Type', ''))

        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            message = data.get("message", "").strip()
            files_data = []  # JSON requests don't support file uploads currently
        else:
            message = request.form.get("message", "").strip()
            # Process file uploads if any
            files_data = []
            files_list = request.files.getlist("files[]")
            if files_list and any(f.filename for f in files_list):
                included_files, excluded_files, total_tokens, file_contents = process_uploaded_files(files_list)
                if excluded_files:
                    error_json = jsonify({
                        "error": "Some files could not be processed",
                        "details": excluded_files,
                    })
                    error_json.status_code = 400
                    return error_json
                files_data = file_contents

        temp_chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id", "")
        if not isinstance(temp_chat_id, str):
            temp_chat_id = str(temp_chat_id)
        chat_id = temp_chat_id

        if not chat_id:
            logger.info("No chat ID found in request header or session. Returning 400.")
            error_json = jsonify({"error": "No chat ID provided"})
            error_json.status_code = 400
            return error_json

        if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
            error_json = jsonify({"error": "Unauthorized access to chat"})
            error_json.status_code = 403
            return error_json

        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            error_json = jsonify({"error": "No model configured"})
            error_json.status_code = 400
            return error_json

        if not message and not files_data:
            error_json = jsonify({"error": "No message or files provided"})
            error_json.status_code = 400
            return error_json

        # Get file content from uploaded files
        file_contents = []
        if 'file_ids' in data:
            from models.uploaded_file import UploadedFile
            for file_id in data['file_ids']:
                file_record = UploadedFile.get_by_id(file_id)
                if file_record and file_record.text_content:
                    file_contents.append({
                        'filename': file_record.filename,
                        'content': file_record.text_content
                    })

        # Combine message + file contents
        combined_message = message
        if file_contents:
            combined_message += "\n\nAttached files:\n" + "\n".join(
                f"[{fc['filename']}]\n{fc['content']}" for fc in file_contents
            )

        # Sanitize user content
        combined_message = bleach.clean(combined_message)

        # Add user message to conversation
        conversation_manager.add_message(
            chat_id=chat_id,
            role="user",
            content=combined_message,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
        )

        # Retrieve updated context
        history = conversation_manager.get_context(
            chat_id, include_system=not model_obj.requires_o1_handling
        )

        # Check streaming via query param
        use_streaming = (
            model_obj.supports_streaming
            and not model_obj.requires_o1_handling
            and request.args.get("stream", "false").lower() == "true"
        )

        if use_streaming:
            return stream_response(chat_id, history, model_obj)
        else:
            return normal_response(chat_id, history, model_obj)

    except Exception as e:
        logger.error("Chat handling error: %s", str(e), exc_info=True)
        error_json = jsonify({"error": "Internal server error"})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/send_stream", methods=["POST"])
@login_required
@limiter.limit("60 per minute")
def handle_chat_stream() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Handle streaming chat messages with dedicated endpoint."""
    try:
        temp_chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id", "")
        if not isinstance(temp_chat_id, str):
            temp_chat_id = str(temp_chat_id)
        chat_id = temp_chat_id

        if not chat_id:
            error_json = jsonify({"error": "No chat ID provided"})
            error_json.status_code = 400
            return error_json

        if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
            error_json = jsonify({"error": "Unauthorized access to chat"})
            error_json.status_code = 403
            return error_json

        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            error_json = jsonify({"error": "No model configured"})
            error_json.status_code = 400
            return error_json

        if not model_obj.supports_streaming or model_obj.requires_o1_handling:
            error_json = jsonify({"error": "Model does not support streaming"})
            error_json.status_code = 400
            return error_json

        history = conversation_manager.get_context(chat_id)
        return stream_response(chat_id, history, model_obj)

    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        error_json = jsonify({"error": "Internal server error"})
        error_json.status_code = 500
        return error_json


def stream_response(chat_id: str, history: List[Dict[str, Any]], model_obj: Model) -> FlaskResponse:
    """Handle streaming responses using AzureOpenAI."""
    logger.debug("Starting stream_response with model_id=%d, model_type=%s", model_obj.id, model_obj.model_type)

    def generate() -> Generator[str, None, None]:
        try:
            client = AzureOpenAI(
                azure_endpoint=model_obj.api_endpoint,
                api_key=model_obj.api_key,
                api_version=model_obj.api_version,
            )

            # Build completion parameters
            completion_params = {
                "model": model_obj.deployment_name,
                "messages": history,
                "max_completion_tokens": model_obj.max_completion_tokens,
                "stream": True
            }

            # Add temperature for o-series models
            if model_obj.model_type and model_obj.model_type.lower() in ["o3-mini", "o1", "o1-mini", "o1-preview"]:
                completion_params["temperature"] = 1.0
            else:
                completion_params["temperature"] = model_obj.temperature

            response = client.chat.completions.create(**completion_params)
            logger.debug("Streaming response initiated, returning SSE chunks")

            for chunk in response:
                # If the chunk is already a string, yield it directly.
                if isinstance(chunk, str):
                    yield chunk
                    continue

                # Try to extract choices from chunk
                choices = None
                if isinstance(chunk, dict):
                    choices = chunk.get("choices")
                elif hasattr(chunk, "choices"):
                    choices = chunk.choices

                if choices:
                    choice = choices[0]
                    delta = None
                    if isinstance(choice, dict):
                        delta = choice.get("delta")
                    elif hasattr(choice, "delta"):
                        delta = choice.delta
                    if delta:
                        content = None
                        if isinstance(delta, dict):
                            content = delta.get("content")
                        elif hasattr(delta, "content"):
                            content = delta.content
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Streaming error: %s", str(e))
            yield f"data: {json.dumps({'error': f'API Error: {str(e)}'})}\n\n"

    return FlaskResponse(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Transfer-Encoding": "chunked"
        }
    )


def normal_response(
    chat_id: str,
    history: List[Dict[str, Any]],
    model_obj: Model
) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Handle normal (non-stream) response while honoring o-series constraints."""
    try:
        if not model_obj:
            error_json = jsonify({"error": "No model configured"})
            error_json.status_code = 400
            return error_json

        logger.debug("Starting normal_response with model_id=%d, model_type=%s", model_obj.id, model_obj.model_type)

        # Determine if this is an o-series model
        model_type = model_obj.model_type or ""
        is_o_series = model_type.lower() in ["o1", "o1-mini", "o1-preview", "o3-mini"]

        # Get max completion tokens with validation
        max_tokens = max(1, getattr(model_obj, "max_completion_tokens", 100000))

        # Validate token limits for o-series models
        if is_o_series:
            token_limits = {
                "o3-mini": 75000,
                "o1": 100000,
                "o1-mini": 50000,
                "o1-preview": 32768
            }
            model_limit = token_limits.get(model_type.lower(), 32768)
            if max_tokens > model_limit:
                max_tokens = model_limit

        # Set up API parameters
        api_params = {
            "messages": history,
            "deployment_name": model_obj.deployment_name,
            "max_completion_tokens": max_tokens,
            "api_endpoint": model_obj.api_endpoint,
            "api_key": model_obj.api_key,
            "api_version": model_obj.api_version,
            "model_type": model_obj.model_type,
            "requires_o1_handling": model_obj.requires_o1_handling,
            "stream": False
        }

        # Add o-series specific parameters
        if is_o_series:
            api_params["temperature"] = 1.0
            # Only add reasoning_effort for o3-mini and o1
            if model_type.lower() in ["o3-mini", "o1"]:
                api_params["reasoning_effort"] = "medium"

        response = get_azure_response(**api_params)
        logger.debug("Raw model response object: %s", response)

        # Extract content with safer attribute checks
        content: Optional[str] = None

        # 1) If response is a dict
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    message_obj = choice.get("message", {})
                    if isinstance(message_obj, dict):
                        content = message_obj.get("content")

        # 2) If response has a `choices` attribute
        elif hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and choice.message is not None:
                content = getattr(choice.message, "content", None)

        # Fallback messages for different scenarios
        if not content:
            if model_obj.requires_o1_handling:
                content = "[No response generated. The model may need more context or a different prompt format.]"
            else:
                content = "[No response from model. Please try again or contact support if this persists.]"

        logger.info("Normal response content length: %d", len(content) if content else 0)

        # Convert raw content to HTML for persistent usage
        content_html = server_side_format_markdown(content)

        # Save the assistant message (no content_html param)
        conversation_manager.add_message(
            chat_id=chat_id,
            role="assistant",
            content=content,  # raw
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
        )

        return jsonify({
            "success": True,
            "message": {
                "role": "assistant",
                "content": content,        # raw text
                "content_html": content_html,  # preformatted HTML
                "id": str(uuid.uuid4()),
            },
        })

    except Exception as e:
        logger.error("Normal response error: %s", str(e), exc_info=True)
        error_json = jsonify({"error": str(e)})
        error_json.status_code = 500
        return error_json

##############################################################################
# 4) Stats & Utility Routes
##############################################################################
@chat_routes.route("/api/log", methods=["POST"])
@login_required
def log_client_event() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Handle client-side event logging from the monitoring system."""
    try:
        log_data = request.get_json()
        if not log_data:
            error_json = jsonify({"error": "No log data provided"})
            error_json.status_code = 400
            return error_json

        log_data.update({
            "user_id": current_user.id,
            "session_id": session.get("id"),
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
            "url": request.headers.get("Referer"),
            "chat_id": log_data.get("chat_id") or session.get("chat_id")
        })

        user_logger = get_logger("user_actions")
        user_logger.info("Client Event:", extra={"client_event": log_data})
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error("Error logging client event: %s", str(e))
        error_json = jsonify({"error": "Internal server error"})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/api/log/error", methods=["POST"])
@login_required
def log_client_error() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Handle client-side error logging from the monitoring system."""
    try:
        error_data = request.get_json()
        if not error_data:
            error_json = jsonify({"error": "No error data provided"})
            error_json.status_code = 400
            return error_json

        error_data.update({
            "user_id": current_user.id,
            "session_id": session.get("id"),
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
            "url": request.headers.get("Referer"),
            "chat_id": error_data.get("chatId") or session.get("chat_id")
        })

        user_logger = get_logger("user_actions")
        user_logger.error("Client Error:", extra={"client_error": error_data})
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error("Error logging client error: %s", str(e))
        error_json = jsonify({"error": "Internal server error"})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/stats/<chat_id>")
@login_required
def get_chat_stats(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Get comprehensive chat statistics including:
    - Total tokens and breakdown by role
    - Message counts and averages
    - Model limits and usage percentages
    - Largest message information
    """
    if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
        error_json = jsonify({"error": "Unauthorized"})
        error_json.status_code = 403
        return error_json

    try:
        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            error_json = jsonify({"error": "Model not found"})
            error_json.status_code = 404
            return error_json

        # Get detailed stats from conversation manager
        stats = conversation_manager.get_usage_stats(chat_id)

        return jsonify({
            "success": True,
            "stats": {
                "total_tokens": stats["total_tokens"],
                "token_breakdown": stats["token_breakdown"],
                "total_messages": stats["total_messages"],
                "message_counts": {
                    "user": stats["user_messages"],
                    "assistant": stats["assistant_messages"],
                    "system": stats["system_messages"]
                },
                "average_tokens_per_message": stats["average_tokens_per_message"],
                "largest_message": stats["largest_message"],
                "model_limits": {
                    "max_tokens": model_obj.max_tokens,
                    "max_completion_tokens": model_obj.max_completion_tokens,
                    "tokens_left": stats["model_limits"]["tokens_left"],
                    "tokens_used_percentage": stats["model_limits"]["tokens_used_percentage"]
                }
            }
        })
    except Exception as e:
        logger.error("Error getting chat stats: %s", str(e), exc_info=True)
        error_json = jsonify({"error": str(e)})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/update_model", methods=["POST"])
@login_required
def update_model() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Update chat model. Expects JSON: { "chat_id": "<id>", "model_id": "<model_id>" }.
    """
    try:
        data = request.get_json() or {}
        chat_id = data.get("chat_id")
        model_id = data.get("model_id")

        if not chat_id or not model_id:
            error_json = jsonify({"error": "Missing required parameters"})
            error_json.status_code = 400
            return error_json

        if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
            error_json = jsonify({"error": "Unauthorized"})
            error_json.status_code = 403
            return error_json

        Chat.update_model_id(chat_id, model_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Error updating model: %s", str(e), exc_info=True)
        error_json = jsonify({"error": str(e)})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/get_chat_context/<chat_id>")
@login_required
def get_chat_context(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Return the current conversation context for a given chat.
    """
    if not validate_chat_access(chat_id):
        error_json = jsonify({"error": "Unauthorized access to chat"})
        error_json.status_code = 403
        return error_json
    try:
        messages = conversation_manager.get_context(chat_id)
        for msg in messages:
            if msg["role"] == "user":
                msg["content"] = bleach.clean(msg["content"])
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        logger.error("Error getting chat context: %s", e)
        error_json = jsonify({"error": "Failed to get chat context"})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Soft-delete a chat if authorized.
    """
    logger.debug("Received request to delete chat_id: %s", chat_id)
    if not validate_chat_access(chat_id):
        logger.warning("Unauthorized delete attempt for chat %s", chat_id)
        error_json = jsonify({"error": "Chat not found or access denied"})
        error_json.status_code = 403
        return error_json
    try:
        Chat.soft_delete(chat_id)
        logger.info("Chat %s deleted successfully", chat_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Error deleting chat %s: %s", chat_id, e)
        error_json = jsonify({"error": "Failed to delete chat"})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/scrape", methods=["POST"])
@login_required
@limiter.limit(SCRAPE_RATE_LIMIT)
def scrape_route() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Handle scraping data from external resources.
    """
    data = request.get_json() or {}
    query = bleach.clean(data.get("query", "").strip())
    if not query:
        error_json = jsonify({"error": "Query is required."})
        error_json.status_code = 400
        return error_json

    try:
        from urllib.parse import urlparse
        domain = urlparse(query).netloc.lower().split(":")[0]
        allowed_domains = {"example.com", "docs.example.org"}  # Adjust for your use case
        if domain not in allowed_domains:
            error_json = jsonify({"error": "Domain not allowed"})
            error_json.status_code = 400
            return error_json

        response = scrape_data(query)
        return jsonify({"response": response})
    except ValueError as ex:
        logger.error("ValueError during scraping: %s", ex)
        error_json = jsonify({"error": str(ex)})
        error_json.status_code = 400
        return error_json
    except Exception as ex:
        logger.error("Error during scraping: %s", str(ex))
        error_json = jsonify({"error": "An error occurred during scraping"})
        error_json.status_code = 500
        return error_json


@chat_routes.route("/update_chat_title/<chat_id>", methods=["POST"])
@login_required
def update_chat_title(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Update the user-defined title of a chat session.
    """
    logger.debug("Received request to update title for chat_id: %s", chat_id)
    if not validate_chat_access(chat_id):
        error_json = jsonify({"error": "Chat not found or access denied"})
        error_json.status_code = 403
        return error_json

    data = request.get_json() or {}
    title = bleach.clean(data.get("title", "").strip())
    if not title or len(title) > 100:
        error_json = jsonify({"error": "Title is required and must be under 100 characters"})
        error_json.status_code = 400
        return error_json

    try:
        Chat.update_title(chat_id, title)
        logger.info("Chat title updated for chat_id: %s", chat_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Error updating chat title: %s", str(e))
        error_json = jsonify({"error": "Failed to update chat title"})
        error_json.status_code = 500
        return error_json
