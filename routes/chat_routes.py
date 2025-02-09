import os
import uuid
from datetime import datetime, timedelta
from typing import Union, Tuple, Dict, Any, Optional, cast

import json
import bleach
import tiktoken
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
from flask_wtf.csrf import validate_csrf, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import text

# Project Imports
from chat_api import get_azure_response, scrape_data
from azure_search_client import AzureOpenAI
from chat_utils import (
    generate_new_chat_id,
    process_uploaded_files,
)
from conversation_manager import conversation_manager
from database import db_session
from models.chat import Chat
from models.model import Model
from models.provider import Provider

# Centralized logging
from logging_config import get_logger

##############################################################################
# Setup
##############################################################################
logger = get_logger(__name__)
token_logger = get_logger("token_usage")

# File Constants
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", default=str(10 * 1024 * 1024)))  # 10 MB
MAX_TOTAL_FILE_SIZE = int(
    os.getenv("MAX_TOTAL_FILE_SIZE", default=str(50 * 1024 * 1024))
)  # 50 MB
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx", "md"}

# Token & Model Constants
DEFAULT_MODEL = "gpt-4"
MODEL_NAME = DEFAULT_MODEL
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", default="8192"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", default="128000"))

# Rate Limiting Constants
SCRAPE_RATE_LIMIT = "5 per minute"
CHAT_RATE_LIMIT = "60 per minute"

# Create the Blueprint with a URL prefix
chat_routes = Blueprint("chat", __name__, url_prefix="/chat")
limiter = Limiter(key_func=get_remote_address)


# ----------------------------------------------------------------------------
# Token Encoding Initialization with Fallback
# ----------------------------------------------------------------------------
def get_token_encoder(model_name: str = DEFAULT_MODEL):
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        logger.warning(f"Model '{model_name}' not found. Using 'cl100k_base'.")
        return tiktoken.get_encoding("cl100k_base")


# Initialize token encoding
encoding = get_token_encoder()


# ----------------------------------------------------------------------------
# Optional: Model Configuration Validation
# ----------------------------------------------------------------------------
# MODEL_CONFIG is assumed to be defined elsewhere. If not, you may define it here.
# For example:
# MODEL_CONFIG = {
#     "gpt-4": { "max_tokens": 8192 },
#     "o1-preview": { "max_tokens": 8300 },
# }
def validate_model_config(model_config: Dict[str, Any]) -> None:
    """
    Validate model configuration and enforce model-specific requirements.
    Uses the standardized MODEL_CONFIG based on model_type.
    """
    model_type = model_config.get("model_type")
    if not model_type:
        raise ValueError("model_type is required")

    # Use MODEL_CONFIG if available
    model_caps = globals().get("MODEL_CONFIG", {}).get(model_type)
    if not model_caps:
        raise ValueError(f"Unsupported model_type: {model_type}")

    # Filter out system messages if present
    messages = model_config.get("messages", [])
    if messages:
        model_config["messages"] = [
            msg for msg in messages if msg.get("role") != "system"
        ]


# ----------------------------------------------------------------------------
# Upload Folder Initialization
# ----------------------------------------------------------------------------
def init_upload_folder() -> None:
    """Initialize the secure upload folder if it doesn't exist."""
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)


init_upload_folder()


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


def validate_model(model: Optional[Any]) -> Optional[str]:
    """
    Validate a model's configuration.
    Returns None if valid; otherwise returns an error message.
    """
    if not model:
        return "No model configured for this chat."

    try:
        # Validate that max_completion_tokens exists and is numeric
        max_completion_tokens = getattr(model, "max_completion_tokens", None)
        if max_completion_tokens is None:
            return "max_completion_tokens is required"

        try:
            max_completion_tokens = int(max_completion_tokens)
        except (TypeError, ValueError):
            return "max_completion_tokens must be a valid integer"

        if max_completion_tokens < 1:
            return "max_completion_tokens must be at least 1"

        # Check provider capabilities
        provider = Provider.get_by_id(getattr(model, "provider_id", None))
        if not provider:
            return "Invalid provider configuration"

        provider_max = provider.capabilities.get("max_tokens", 16384)

        # Check that model_type is provided
        model_type = getattr(model, "model_type", "")
        if not model_type:
            return "model_type is required"

        requires_o1 = getattr(model, "requires_o1_handling", False)
        is_o1_preview = model_type.lower() == "o1-preview" and requires_o1

        if is_o1_preview:
            if max_completion_tokens > 8300:
                return "max_completion_tokens must be between 1 and 8300 for o1-preview models"
        else:
            if max_completion_tokens > provider_max:
                return f"max_completion_tokens must be between 1 and {provider_max}"

        return None

    except Exception as e:
        logger.error(f"Model validation error: {str(e)}")
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
        csrf_token = request_data.form.get("csrf_token")
        if not csrf_token:
            return {"valid": False, "error": "Missing CSRF token"}

        try:
            validate_csrf(csrf_token)
        except CSRFError as e:
            logger.error("CSRF token validation failed: %s", str(e))
            return {"valid": False, "error": "Invalid CSRF token"}

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
    Checks for models, creates new chat if needed, and renders chat.html.
    """
    try:
        with db_session() as db:
            model_count = db.execute(text("SELECT COUNT(*) FROM models")).scalar()
            if model_count == 0:
                logger.warning("No models found - showing error message")
                return render_template(
                    "error.html",
                    error=(
                        "No AI models are configured. Please contact your administrator "
                        "or create a new model in the Models section."
                    ),
                    show_models_link=True,
                )

        # Create a new chat automatically for /interface
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        Chat.create(chat_id=chat_id, user_id=user_id, title="New Chat")
        session["chat_id"] = chat_id

        # Attach default model if none
        chat = Chat.get_by_id(chat_id)
        model_obj = Chat.get_model(chat_id) if chat.model_id else None
        if not model_obj:
            model_obj = Model.get_default()
            if model_obj:
                chat.model_id = model_obj.id
                Chat.update_model_id(chat_id, model_obj.id)

        chat_title = chat.title
        model_name = model_obj.name if model_obj else "Default Model"
        current_model = model_obj

        # Get Azure token
        azure_token = None
        if model_obj and model_obj.api_key:
            try:
                from utils.encryption import decrypt_api_key

                encryption_key = os.getenv("ENCRYPTION_KEY", None)
                if encryption_key and model_obj.api_key:
                    azure_token = decrypt_api_key(model_obj.api_key, encryption_key)
                else:
                    azure_token = None
                    logger.warning("Azure token not decrypted because ENCRYPTION_KEY or api_key is empty.")
            except Exception as e:
                logger.error("Error decrypting Azure token: %s", str(e))

        return cast(
            FlaskResponse,
            render_template(
                "chat.html",
                chat_id=chat_id,
                chat_title=chat_title,
                model_name=model_name,
                current_model=current_model,
                messages=[],
                models=Model.get_all(),
                conversations=Chat.get_user_chats(current_user.id),
                now=datetime.now,
                today=datetime.now().strftime("%Y-%m-%d"),
                yesterday=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                azure_token=azure_token,
            ),
        )
    except Exception as e:
        logger.error("Error initializing chat interface: %s", str(e))
        return make_response(jsonify({"error": "Internal server error"}), 500)


@chat_routes.route("/chat_interface", methods=["GET"])
@login_required
def chat_interface() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    GET /chat/chat_interface
    Renders chat.html for an existing or new chat ID, plus existing messages.
    """
    logger.debug("Current user: id=%s, role=%s", current_user.id, current_user.role)
    chat_id: Optional[str] = request.args.get("chat_id") or session.get("chat_id")
    if request.args.get("chat_id"):
        session["chat_id"] = chat_id

    # If no chat_id or the chat doesn't exist, create new
    if not chat_id or not Chat.get_by_id(chat_id):
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)
        try:
            with db_session() as db:
                model_count = db.execute(text("SELECT COUNT(*) FROM models")).scalar()
                if model_count == 0:
                    return render_template(
                        "error.html",
                        error=(
                            "No AI models are configured. Please contact your administrator "
                            "or create a new model in the Models section."
                        ),
                        show_models_link=True,
                    )
            Chat.create(chat_id=chat_id, user_id=user_id, title="New Chat")
            session["chat_id"] = chat_id
            return redirect(url_for("chat.index"))
        except Exception as e:
            logger.error("Error creating chat: %s", e)
            return (
                cast(
                    FlaskResponse,
                    render_template(
                        "error.html",
                        error="Could not initialize chat. Please contact an administrator.",
                    ),
                ),
                500,
            )

    chat = Chat.get_by_id(chat_id)
    if not chat:
        logger.error("Chat %s not found", chat_id)
        return cast(FlaskResponse, redirect(url_for("chat.chat_interface")))

    try:
        # Get or fallback to default model
        model_obj = Chat.get_model(chat_id) if chat.model_id else None
        if not model_obj and chat.model_id:
            logger.error("Failed to retrieve model for chat %s.", chat_id)
            return (
                cast(
                    FlaskResponse,
                    render_template(
                        "error.html",
                        error="The model configuration is invalid. Please contact an administrator.",
                    ),
                ),
                500,
            )
        chat_title = chat.title
        model_name = model_obj.name if model_obj else "Default Model"

        # Get Azure token
        azure_token = None
        if model_obj and model_obj.api_key:
            try:
                from utils.encryption import decrypt_api_key

                encryption_key = os.getenv("ENCRYPTION_KEY", "")
                azure_token = decrypt_api_key(model_obj.api_key, encryption_key)
            except Exception as e:
                logger.error("Error decrypting Azure token: %s", str(e))

        current_model = model_obj
    except Exception as e:
        logger.error("Error retrieving model for chat %s: %s", chat_id, str(e))
        return (
            cast(
                FlaskResponse,
                render_template(
                    "error.html",
                    error="An error occurred while retrieving the model configuration.",
                ),
            ),
            500,
        )

    # Get existing messages
    messages = conversation_manager.get_context(chat_id)
    for message in messages:
        # Bleach any user content
        if message["role"] == "user":
            message["content"] = bleach.clean(message["content"])

    # Collect list of all models for the dropdown
    models = Model.get_all()
    models_serialized = []
    for m in models:
        models_serialized.append(
            {
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
            }
        )

    conversations = Chat.get_user_chats(current_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Prepare a minimal dictionary for the current model
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

    return cast(
        FlaskResponse,
        render_template(
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
        ),
    )


##############################################################################
# 2) Create a New Chat (Replaces /new_chat)
##############################################################################
@chat_routes.route("/new", methods=["POST"])
@login_required
def new_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Create a new chat session and return the new chat_id.
    (Replacing the old /new_chat route.)
    """
    try:
        chat_id = str(uuid.uuid4())
        Chat.create(chat_id=chat_id, user_id=current_user.id, title="New Chat")
        return jsonify({"success": True, "chat_id": chat_id})
    except Exception as e:
        logger.error(f"Error creating new chat: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_routes.after_request
def add_cors_headers(response):
    """Add required CORS headers for streaming support"""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Chat-ID, api-key"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Accel-Buffering"] = "no"  # Disable buffering for nginx
    return response


##############################################################################
# 3) Send a Chat Message (Replaces the Old handle_chat Route)
##############################################################################
@chat_routes.route("/send", methods=["POST"])
@login_required
@limiter.limit("60 per minute")
def handle_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Handle chat messages with optional file uploads, returning streaming or normal.
    This replaces the old /chat/send route from the original code.
    """
    try:
        logger.info(f"handle_chat: form data keys = {list(request.form.keys())}, files = {len(request.files) if request.files else 0}")
        # Validate chat access
        chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id")
        if not chat_id:
            logger.info("No chat ID found in request header or session. Returning 400.")
            return jsonify({"error": "No chat ID provided"}), 400

        if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
            return jsonify({"error": "Unauthorized access to chat"}), 403

        # Get model
        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            return jsonify({"error": "No model configured"}), 400

        # Retrieve user message
        message = request.form.get("message", "").strip()
        if not message and not request.files:
            return jsonify({"error": "No message or files provided"}), 400

        try:
            # Process file uploads if any
            files_data = []
            if request.files:
                included_files, excluded_files, total_tokens, file_contents = (
                    process_uploaded_files(request.files.getlist("files[]"))
                )
                if excluded_files:
                    return (
                        jsonify(
                            {
                                "error": "Some files could not be processed",
                                "details": excluded_files,
                            }
                        ),
                        400,
                    )
                files_data = file_contents

            # Combine message + file contents
            combined_message = message
            if files_data:
                combined_message += "\n\nAttached files:\n" + "\n".join(
                    f"[{f['filename']}]\n{f['content']}" for f in files_data
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

            # Check if streaming is requested
            use_streaming = (
                model_obj.supports_streaming
                and not model_obj.requires_o1_handling
                and request.headers.get("Accept") == "text/event-stream"
            )

            if use_streaming:
                return stream_response(chat_id, history, model_obj)
            else:
                return normal_response(chat_id, history, model_obj)

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        logger.error(f"Chat handling error: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


def stream_response(chat_id: str, history: list, model_obj: Model) -> Response:
    """Handle streaming responses using proper Azure SDK."""

    def generate():
        try:
            # Create the Azure OpenAI client
            client = AzureOpenAI(
                azure_endpoint=model_obj.api_endpoint,
                api_key=model_obj.api_key,
                api_version=model_obj.api_version,
            )

            # Request a streaming chat completion from the Azure OpenAI service
            response = client.chat.completions.create(
                model=model_obj.deployment_name,
                messages=history,
                temperature=model_obj.temperature,
                max_tokens=model_obj.max_completion_tokens,
                stream=True,
            )

            # Process each chunk of the streamed response
            for chunk in response:
                # Ensure the chunk contains valid choices and content
                if chunk.choices and chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            yield f"data: {json.dumps({'error': f'API Error: {str(e)}'})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


def normal_response(
    chat_id: str, history: list, model_obj: Model
) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Handle normal (non-stream) response while honoring o-series constraints.
    For o-series (e.g. o1, o3-mini), remove unsupported parameters (like temperature),
    rely on 'max_completion_tokens', and optionally pass 'reasoning_effort' if set.
    Developer messages can also be used in place of system if needed.
    """
    try:
        # If this is an o-series model, remove typical temperature usage.
        # Also allow 'reasoning_effort' if set, else default to 'medium'.
        is_o_series = model_obj.model_type in ["o1", "o1-mini", "o1-preview", "o3-mini"]
        reasoning_effort_value = "medium"
        if hasattr(model_obj, "reasoning_effort") and model_obj.reasoning_effort:
            reasoning_effort_value = model_obj.reasoning_effort

        response = get_azure_response(
            messages=history,
            deployment_name=model_obj.deployment_name,
            max_completion_tokens=model_obj.max_completion_tokens,
            api_endpoint=model_obj.api_endpoint,
            api_key=model_obj.api_key,
            api_version=model_obj.api_version,
            model_type=model_obj.model_type,
            requires_o1_handling=model_obj.requires_o1_handling,
            # For o-series, extra param 'reasoning_effort' is possible.
            reasoning_effort=reasoning_effort_value if is_o_series else None,
            # If using an o-series, skip sending "temperature", "top_p", etc.
            store_completion=False,
            stream=False,
        )

        # Proper response validation
        if not isinstance(response, dict):
            raise ValueError("Invalid response format from API")

        choices = response.get("choices")
        if not choices or not isinstance(choices, list):
            raise ValueError("No choices in API response")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ValueError("Invalid choice format in API response")

        message = first_choice.get("message")
        if not message or not isinstance(message, dict):
            raise ValueError("Invalid message format in API response")

        content = message.get("content")
        if content is None:
            raise ValueError("No content in API response")

        # Save to conversation
        conversation_manager.add_message(
            chat_id=chat_id,
            role="assistant",
            content=content,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
        )

        return jsonify(
            {
                "success": True,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "id": str(uuid.uuid4()),
                },
            }
        )

    except Exception as e:
        logger.error(f"Normal response error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


##############################################################################
# 4) Stats & Utility Routes
##############################################################################
@chat_routes.route("/api/log/error", methods=["POST"])
@login_required
def log_client_error() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Handle client-side error logging from the monitoring system."""
    try:
        error_data = request.get_json()
        if not error_data:
            return jsonify({"error": "No error data provided"}), 400

        # Enrich error data with request context
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

        # Log the error with client context
        logger = get_logger("user_actions")
        logger.error("Client Error:", extra={"client_error": error_data})
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error logging client error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@chat_routes.route("/stats/<chat_id>")
@login_required
def get_chat_stats(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Get chat statistics: total tokens, breakdown, model limits, etc.
    (Replaces the old /chat/stats/<chat_id> route.)
    """
    if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            return jsonify({"error": "Model not found"}), 404

        stats = conversation_manager.get_usage_stats(chat_id)
        return jsonify(
            {
                "success": True,
                "stats": {
                    "total_tokens": stats.get("total_tokens", 0),
                    "token_breakdown": stats.get("token_breakdown", {}),
                    "model_limits": {"max_tokens": model_obj.max_tokens},
                },
            }
        )
    except Exception as e:
        logger.error(f"Error getting chat stats: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_routes.route("/update_model", methods=["POST"])
@login_required
def update_model() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Update chat model (Replaces old /chat/update_model route).
    Expects JSON: { "chat_id": "<id>", "model_id": "<model_id>" }.
    """
    try:
        data = request.get_json() or {}
        chat_id = data.get("chat_id")
        model_id = data.get("model_id")

        if not chat_id or not model_id:
            return jsonify({"error": "Missing required parameters"}), 400

        if not Chat.can_access_chat(chat_id, current_user.id, current_user.role):
            return jsonify({"error": "Unauthorized"}), 403

        # Validate and update
        Chat.update_model_id(chat_id, model_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating model: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_routes.route("/get_chat_context/<chat_id>")
@login_required
def get_chat_context(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Return the current conversation context for a given chat.
    """
    if not validate_chat_access(chat_id):
        return jsonify({"error": "Unauthorized access to chat"}), 403
    try:
        messages = conversation_manager.get_context(chat_id)
        for msg in messages:
            if msg["role"] == "user":
                msg["content"] = bleach.clean(msg["content"])
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        logger.error("Error getting chat context: %s", e)
        return jsonify({"error": "Failed to get chat context"}), 500


@chat_routes.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Soft-delete a chat if authorized.
    """
    logger.debug("Received request to delete chat_id: %s", chat_id)
    if not validate_chat_access(chat_id):
        logger.warning("Unauthorized delete attempt for chat %s", chat_id)
        return jsonify({"error": "Chat not found or access denied"}), 403
    try:
        Chat.soft_delete(chat_id)
        logger.info("Chat %s deleted successfully", chat_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Error deleting chat %s: %s", chat_id, e)
        return jsonify({"error": "Failed to delete chat"}), 500


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
def update_chat_title(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Update the user-defined title of a chat session.
    """
    logger.debug("Received request to update title for chat_id: %s", chat_id)
    if not validate_chat_access(chat_id):
        return jsonify({"error": "Chat not found or access denied"}), 403

    data = request.get_json() or {}
    title = bleach.clean(data.get("title", "").strip())
    if not title or len(title) > 100:
        return (
            jsonify({"error": "Title is required and must be under 100 characters"}),
            400,
        )

    try:
        Chat.update_title(chat_id, title)
        logger.info("Chat title updated for chat_id: %s", chat_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Error updating chat title: %s", str(e))
        return jsonify({"error": "Failed to update chat title"}), 500
