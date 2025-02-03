import os
import re
import uuid
import traceback
from datetime import datetime, timedelta
import bleach
from typing import Union, Tuple, List, Dict, Any, Optional, cast
import tiktoken
from werkzeug.utils import secure_filename
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
    Response as FlaskResponse,
    current_app,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import login_required, current_user
from flask_wtf.csrf import validate_csrf, CSRFError
from sqlalchemy import text

from chat_api import get_azure_response, scrape_data
from chat_utils import (
    allowed_file,
    generate_chat_title,
    generate_new_chat_id,
    process_file,
    count_tokens,
)
from conversation_manager import conversation_manager
from database import db_session, is_initialized, get_db_state
from models.chat import Chat
from models.model import Model
from models.provider import Provider

# Import centralized logging configuration
from logging_config import get_logger

# Get loggers
logger = get_logger(__name__)
token_logger = get_logger("token_usage")

# File Constants
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", default=str(10 * 1024 * 1024)))  # 10 MB
MAX_TOTAL_FILE_SIZE = int(os.getenv("MAX_TOTAL_FILE_SIZE", default=str(50 * 1024 * 1024)))  # 50 MB
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx", "md"}

# Token Constants
DEFAULT_MODEL = "gpt-4"
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", default="8192"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", default="128000"))
MODEL_NAME = DEFAULT_MODEL

# Rate Limiting Constants
SCRAPE_RATE_LIMIT = "5 per minute"
CHAT_RATE_LIMIT = "60 per minute"

##############################################################################
# 1) Give your blueprint a URL prefix so routes map to /chat/... in the browser
##############################################################################
chat_routes = Blueprint("chat", __name__)
limiter = Limiter(key_func=get_remote_address)

try:
    encoding = tiktoken.encoding_for_model(DEFAULT_MODEL)
except KeyError:
    logger.warning("Model '%s' not found. Falling back to 'cl100k_base'.", DEFAULT_MODEL)
    encoding = tiktoken.get_encoding("cl100k_base")


def init_upload_folder() -> None:
    """Initialize the secure upload folder."""
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)


init_upload_folder()


def validate_chat_access(chat_id: Optional[str]) -> bool:
    if not chat_id or not isinstance(chat_id, str):
        return False
    return Chat.can_access_chat(chat_id, current_user.id, current_user.role)


def validate_model(model: Optional[Any]) -> Optional[str]:
    """Validate the model configuration."""
    if not model:
        return "No model configured for this chat."

    try:
        # Validate max_completion_tokens
        max_completion_tokens = getattr(model, "max_completion_tokens", None)
        if not isinstance(max_completion_tokens, int):
            try:
                max_completion_tokens = int(max_completion_tokens)
            except (TypeError, ValueError):
                return "max_completion_tokens must be a valid integer"

        # Base validation - ensure it's at least 1
        if not isinstance(max_completion_tokens, int) or max_completion_tokens < 1:
            return "max_completion_tokens must be at least 1"

        # Get provider capabilities
        provider = Provider.get_by_id(model.provider_id)
        provider_max = provider.capabilities.get('max_tokens', 16384) if provider else 16384

        # Get model type and determine if it's an o1-preview model
        model_type = getattr(model, "model_type", "").lower()
        requires_o1 = getattr(model, "requires_o1_handling", False)
        is_o1_preview = model_type == "o1-preview" and requires_o1

        # Apply appropriate validation based on model type
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
    """Safely retrieve the model's max_tokens, or fallback."""
    max_tokens = getattr(model_obj, "max_tokens", None)
    if isinstance(max_tokens, int) and max_tokens > 0:
        return max_tokens
    return 16384


def truncate_content(text: str, max_tokens: int, truncation_note: str) -> str:
    try:
        encoding = tiktoken.encoding_for_model(DEFAULT_MODEL)
    except KeyError:
        logger.warning("Model '%s' not found. Using 'cl100k_base'.", DEFAULT_MODEL)
        encoding = tiktoken.get_encoding("cl100k_base")

    tokens = encoding.encode(text)
    note_tokens = encoding.encode(truncation_note)
    allowed = max_tokens - len(note_tokens)
    truncated_tokens = tokens[:allowed]
    truncated_text = encoding.decode(truncated_tokens)
    return truncated_text + truncation_note


def process_uploaded_files(files: List[Any]) -> Tuple[List[Dict], List[Dict], int, List[Dict]]:
    included_files = []
    excluded_files = []
    total_tokens = 0
    file_contents = []

    for file in files:
        if not file or not file.filename:
            continue

        if not allowed_file(file.filename):
            excluded_files.append({"filename": file.filename or "Unknown", "error": "Invalid file type"})
            continue

        try:
            filename = secure_filename(file.filename)
            # Get file metadata
            file_size = file.content_length or 0
            file_type = file.content_type or 'text/plain'

            # Read file content
            content = file.read().decode('utf-8', errors='ignore')
            tokens = count_tokens(content, MODEL_NAME)

            if total_tokens + tokens > MAX_INPUT_TOKENS:
                excluded_files.append({"filename": filename, "error": "Exceeds token limit"})
                continue

            # Format file info
            file_info = {
                "filename": filename,
                "size": f"{file_size / 1024:.1f}KB",
                "type": file_type,
                "token_count": tokens
            }

            included_files.append(file_info)
            file_contents.append({
                "filename": filename,
                "content": content,
                "metadata": {
                    "size": file_size,
                    "type": file_type,
                    "tokens": tokens,
                    "timestamp": datetime.now().isoformat()
                }
            })
            total_tokens += tokens

        except Exception as e:
            logger.error("Error processing file %s: %s", file.filename, e)
            excluded_files.append({"filename": file.filename, "error": str(e)})

    return included_files, excluded_files, total_tokens, file_contents


##############################################################################
# 2) Routes for /chat interface
##############################################################################

@chat_routes.route("/interface")
@login_required
def index() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Equivalent to GET /chat/interface
    Checks for models, creates new chat if needed, renders chat.html
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

        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)

        Chat.create(chat_id=chat_id, user_id=user_id, title="New Chat")
        session["chat_id"] = chat_id

        chat = Chat.get_by_id(chat_id)
        model_obj = Chat.get_model(chat_id) if chat.model_id else None

        # If no model, fetch default
        if not model_obj:
            model_obj = Model.get_default()
            if model_obj:
                chat.model_id = model_obj.id
                Chat.update_model_id(chat_id, model_obj.id)

        chat_title = chat.title
        model_name = model_obj.name if model_obj else "Default Model"
        current_model = model_obj

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
            ),
        )
    except Exception as e:
        logger.error("Error initializing chat interface: %s", str(e))
        return make_response(jsonify({"error": "Internal server error"}), 500)


@chat_routes.route("/new_chat", methods=["GET", "POST"])
@login_required
def new_chat_route() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Create a new chat and return success JSON or render the form."""
    logger.debug("New chat request from user %s", current_user.id)
    try:
        chat_id = generate_new_chat_id()
        user_id = int(current_user.id)

        Chat.create(chat_id=chat_id, user_id=user_id, title="New Chat")
        session["chat_id"] = chat_id
        logger.info("New chat created with ID: %s", chat_id)

        if request.method == "POST":
            return jsonify({"success": True, "chat_id": chat_id})
        return cast(FlaskResponse, render_template("new_chat.html"))

    except ValueError as e:
        logger.warning("No models found - showing error message: %s", str(e))
        return (
            jsonify(
                {
                    "error": "No AI models are configured. Please contact your administrator or create a new model in the Models section.",
                    "show_models_link": True,
                }
            ),
            400,
        )
    except Exception as e:
        logger.error("Failed to create new chat", exc_info=True)
        return make_response(
            jsonify({"error": "Failed to create new chat"}),
            500,
        )


##############################################################################
# 3) Separate route for handle_chat (POST) => /chat/ with blueprint prefix
##############################################################################

@chat_routes.route("/chat/send", methods=["POST"]) 
@login_required
@limiter.limit(CHAT_RATE_LIMIT)
def handle_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """POST /chat/send - Handle chat messages (either streaming or normal)."""
    try:
        logger.info(
            "Chat request received - IP: %s, User-Agent: %s, User: %s",
            request.remote_addr,
            request.headers.get("User-Agent"),
            current_user.id if current_user.is_authenticated else "anonymous",
        )

        validation_result = validate_chat_request(request)
        if not validation_result["valid"]:
            logger.error(
                "Chat request validation failed: %s - IP: %s, User: %s",
                validation_result["error"],
                request.remote_addr,
                current_user.id if current_user.is_authenticated else "anonymous",
            )
            return jsonify({"error": validation_result["error"]}), 400

        chat_id = validation_result["chat_id"]
        model_obj = Chat.get_model(chat_id)
        model_error = validate_model(model_obj)
        if model_error:
            logger.error("Model validation failed for chat %s: %s", chat_id, model_error)
            return jsonify({"error": model_error}), 400

        # Gather message or files
        message = request.form.get("message", "").strip()
        if not message and not request.files:
            logger.warning("No message or files provided")
            return jsonify({"error": "Message or files are required."}), 400

        # Process uploaded files and build message
        included_files, excluded_files, file_tokens, file_contents = process_uploaded_files(
            request.files.getlist("files[]")
        )
        total_tokens = file_tokens

        # Count message tokens
        if message:
            try:
                message_tokens = count_tokens(message, MODEL_NAME)
            except KeyError:
                logger.warning("Model '%s' not found for token counting.", MODEL_NAME)
                message_tokens = len(encoding.encode(message))
            total_tokens += message_tokens

        # Build the combined message with proper formatting
        combined_message = []

        # Add user message if present
        if message:
            combined_message.append(message)

        # Add file contents with metadata
        if file_contents:
            combined_message.append("\nI'm sharing some files with you:")
            for file in file_contents:
                combined_message.append(f"\n[File: {file['filename']}]")
                combined_message.append(f"Type: {file['metadata']['type']}")
                combined_message.append(f"Size: {file['metadata']['size']} bytes")
                combined_message.append(f"Tokens: {file['metadata']['tokens']}")
                combined_message.append("Content:\n```")
                combined_message.append(file['content'])
                combined_message.append("```\n")

        # Add Azure file IDs if present
        file_ids = request.form.getlist('file_ids[]')
        if file_ids:
            from models.uploaded_file import UploadedFile
            azure_files = []
            for file_id in file_ids:
                file_record = UploadedFile.get_by_id(file_id)
                if file_record and file_record.azure_file_id:
                    azure_files.append({
                        'id': file_record.azure_file_id,
                        'name': file_record.filename
                    })
                    logger.info(f"Added Azure file ID {file_record.azure_file_id} for file {file_record.filename}")
                else:
                    logger.warning(f"No Azure file ID found for file {file_id}")

            if azure_files:
                combined_message.append("\nAdditional files available in Azure:")
                for file in azure_files:
                    combined_message.append(f"- {file['name']} (ID: {file['id']})")

        # Join all message parts
        combined_message = "\n".join(filter(None, combined_message))

        # If total tokens > max, truncate
        if total_tokens > MAX_INPUT_TOKENS:
            combined_message = truncate_content(
                combined_message,
                MAX_INPUT_TOKENS,
                "\n\n[Note: Content truncated due to token limit.]",
            )
            logger.info("Input content truncated due to token limit")

        # Log file processing results
        if included_files:
            logger.info("Processed files: %s", [f["filename"] for f in included_files])
            logger.info("File tokens: %d", file_tokens)

        combined_message = bleach.clean(combined_message)
        logger.info(
            "Message received - Chat: %s, User: %s, Length: %d, Files: %d",
            chat_id,
            current_user.id,
            len(combined_message),
            len(included_files),
        )

        # Possibly update chat title after ~5 messages
        if Chat.is_title_default(chat_id) and len(conversation_manager.get_context(chat_id)) >= 5:
            conversation_text = "\n".join(
                f"{msg['role']}: {msg['content']}"
                for msg in conversation_manager.get_context(chat_id)[:5]
            )
            Chat.update_title(chat_id, generate_chat_title(conversation_text))

        # Get conversation history
        history = conversation_manager.get_context(
            chat_id,
            include_system=not getattr(model_obj, "requires_o1_handling", False),
        )

        # Define max_tokens and api_version
        max_tokens = model_obj.max_completion_tokens
        api_version = model_obj.api_version

        # Count tokens for the combined message
        message_tokens = count_tokens(combined_message, MODEL_NAME)
        total_tokens = message_tokens + file_tokens

        # Count tokens for the combined message
        message_tokens = count_tokens(combined_message, MODEL_NAME)
        total_tokens += message_tokens

        # If total tokens exceed limit, truncate the message
        if total_tokens > MAX_INPUT_TOKENS:
            combined_message = truncate_content(
                combined_message,
                MAX_INPUT_TOKENS,
                "\n\n[Note: Content truncated due to token limit.]",
            )
            logger.info("Input content truncated due to token limit")

        # Log included and excluded files
        if included_files:
            logger.info("Processed files: %s", [f["filename"] for f in included_files])
            logger.info("File tokens: %d", file_tokens)

        # Sanitize the combined message
        combined_message = bleach.clean(combined_message)

        # Add the combined message to the conversation
        conversation_manager.add_message(
            chat_id=chat_id,
            role="user",
            content=combined_message,
            model_max_tokens=getattr(model_obj, "max_tokens", None),
            requires_o1_handling=getattr(model_obj, "requires_o1_handling", False),
        )

        # Check streaming
        use_streaming = (
            getattr(model_obj, "supports_streaming", False)
            and not getattr(model_obj, "requires_o1_handling", False)
            and request.headers.get("Accept") == "text/event-stream"
        )

        # Get app instance once
        app = current_app._get_current_object()

        if use_streaming:
            # SSE streaming response
            def generate():
                try:
                    # Use app context from outer scope
                    with app.app_context():
                        # Verify API version
                        api_version = getattr(model_obj, "api_version", "2024-12-01-preview")
                        if not api_version:
                            logger.error("API version not configured for this model")
                            raise RuntimeError("API version is not configured")
                        # Check database initialization
                        db_state = get_db_state()
                        if not db_state.get("initialized"):
                            logger.error("Database not properly initialized")
                            raise RuntimeError("Database not initialized. Please try again.")

                        try:
                            # Get provider capabilities
                            provider = Provider.get_by_id(model_obj.provider_id)
                            provider_caps = provider.capabilities if provider else {}

                            # Apply provider-specific settings
                            max_tokens = min(
                                model_obj.max_completion_tokens,
                                provider_caps.get('max_tokens', 16384)
                            )
                            temperature = 1.0 if provider_caps.get('fixed_temperature') else model_obj.temperature

                            response_generator = get_azure_response(
                                messages=history,
                                deployment_name=model_obj.deployment_name,
                                max_completion_tokens=max_tokens,
                                api_endpoint=model_obj.api_endpoint,
                                api_key=model_obj.api_key,
                                api_version=api_version,
                                requires_o1_handling=model_obj.requires_o1_handling,
                                timeout_seconds=120,
                                stream=True
                            )
                        except Exception as api_err:
                            logger.error("Azure API error: %s", str(api_err))
                            yield f"data: [ERROR] Failed to get response from Azure API: {str(api_err)}\n\n"
                            return

                        accumulated = ""
                        for chunk in response_generator:
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                # Process chunk in the same way as non-streaming response
                                if "message" in chunk["choices"][0] and "content" in chunk["choices"][0]["message"]:
                                    content = chunk["choices"][0]["message"]["content"]
                                else:
                                    content = str(chunk["choices"][0].get("text", ""))

                                if content:
                                    accumulated += content
                                    yield f"data: {content}\n\n"

                        try:
                            # Process content to prevent Jinja2 injection
                            content_processed = accumulated.replace("{%", "&#123;%").replace("%}", "%&#125;")
                            conversation_manager.add_message(
                                chat_id=chat_id,
                                role="assistant",
                                content=content_processed,
                                model_max_tokens=get_model_token_limit(model_obj),
                                requires_o1_handling=model_obj.requires_o1_handling,
                            )
                            yield "data: [DONE]\n\n"
                        except Exception as save_error:
                            logger.error("Error saving response: %s", str(save_error))
                            # Still try to save the message even if we can't stream it
                            try:
                                content_processed = accumulated.replace("{%", "&#123;%").replace("%}", "%&#125;")
                                conversation_manager.add_message(
                                    chat_id=chat_id,
                                    role="assistant",
                                    content=content_processed,
                                    model_max_tokens=get_model_token_limit(model_obj),
                                    requires_o1_handling=model_obj.requires_o1_handling,
                                )
                            except Exception as final_error:
                                logger.error("Failed to save response: %s", str(final_error))
                            yield f"data: [ERROR] {str(save_error)}\n\n"
                except Exception as e:
                    logger.error("Streaming error: %s", str(e))
                    # Try to save whatever we accumulated
                    if accumulated:
                        try:
                            content_processed = accumulated.replace("{%", "&#123;%").replace("%}", "%&#125;")
                            conversation_manager.add_message(
                                chat_id=chat_id,
                                role="assistant",
                                content=content_processed,
                                model_max_tokens=get_model_token_limit(model_obj),
                                requires_o1_handling=model_obj.requires_o1_handling,
                            )
                        except Exception as save_error:
                            logger.error("Failed to save partial response: %s", str(save_error))
                    yield f"data: [ERROR] {str(e)}\n\n"

            response = Response(generate(), mimetype="text/event-stream")
            response.headers["Cache-Control"] = "no-cache"
            return response

        else:
            # Normal (non-stream) response
            try:
                # Wrap entire response handling in app context
                with app.app_context():
                    # Check database initialization
                    db_state = get_db_state()
                    if not db_state.get("initialized"):
                        logger.error("Database not properly initialized")
                        return jsonify({
                            "error": "Database not initialized. Please try again."
                        }), 503  # Service Unavailable

                    # Get conversation history
                    history = conversation_manager.get_context(
                        chat_id,
                        include_system=not getattr(model_obj, "requires_o1_handling", False),
                    )

                    # Verify API version
                    api_version = getattr(model_obj, "api_version", "2024-12-01-preview")
                    if not api_version:
                        logger.error("API version not configured for this model")
                        return jsonify({
                            "error": "API version is not configured"
                        }), 500

                    # Get provider capabilities
                    provider = Provider.get_by_id(model_obj.provider_id)
                    provider_caps = provider.capabilities if provider else {}

                    # Apply provider-specific settings
                    max_tokens = min(
                        model_obj.max_completion_tokens,
                        provider_caps.get('max_tokens', 16384)
                    )
                    temperature = 1.0 if provider_caps.get('fixed_temperature') else model_obj.temperature

                    # Get Azure response
                    response = get_azure_response(
                        messages=history,
                        deployment_name=model_obj.deployment_name,
                        max_completion_tokens=max_tokens,
                        api_endpoint=model_obj.api_endpoint,
                        api_key=model_obj.api_key,
                        api_version=api_version,
                        requires_o1_handling=model_obj.requires_o1_handling,
                        timeout_seconds=120,
                        stream=False
                    )

                    # Process response
                    if isinstance(response, dict):
                        if "choices" in response and len(response["choices"]) > 0:
                            content = response["choices"][0]["message"]["content"]
                        else:
                            content = str(response)
                    elif isinstance(response, str):
                        content = response
                    else:
                        content = str(response)

                    # Prevent Jinja2 injection
                    content_processed = content.replace("{%", "&#123;%").replace("%}", "%&#125;")

                    # Add message to conversation
                    conversation_manager.add_message(
                        chat_id=chat_id,
                        role="assistant",
                        content=content_processed,
                        model_max_tokens=get_model_token_limit(model_obj),
                        requires_o1_handling=model_obj.requires_o1_handling,
                    )

                    return jsonify(
                        {
                            "message": {
                                "role": "assistant",
                                "content": content_processed,
                                "id": str(uuid.uuid4()),
                            }
                        }
                    )

            except Exception as api_err:
                logger.error("Azure API error: %s", str(api_err))
                return jsonify({
                    "error": f"Failed to get response from Azure API: {str(api_err)}"
                }), 500

    except Exception as e:
        logger.error("Error during chat handling: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


##############################################################################
# 4) Chat Interface and Stats
##############################################################################

@chat_routes.route("/chat_interface", methods=["GET"])
@login_required
def chat_interface() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    GET /chat/chat_interface
    Renders chat.html with an existing or new Chat ID, plus messages
    """
    logger.debug("Current user: id=%s, role=%s", current_user.id, current_user.role)
    chat_id: Optional[str] = request.args.get("chat_id") or session.get("chat_id")
    if request.args.get("chat_id"):
        session["chat_id"] = chat_id

    if not chat_id or not Chat.get_by_id(chat_id):
        # Create new chat if none exists
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

    messages = conversation_manager.get_context(chat_id)
    for message in messages:
        if message["role"] == "assistant":
            continue
        elif message["role"] == "user":
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
            "max_tokens": m.max_tokens
        })

    conversations = Chat.get_user_chats(current_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Prepare current model data
    current_model_data = None
    if current_model:
        current_model_data = {
            'id': current_model.id,
            'name': current_model.name,
            'model_type': current_model.model_type,
            'requires_o1_handling': current_model.requires_o1_handling,
            'supports_streaming': current_model.supports_streaming,
            'max_completion_tokens': current_model.max_completion_tokens
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
        ),
    )


@chat_routes.route("/get_chat_context/<chat_id>")
@login_required
def get_chat_context(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
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
def scrape() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    data = request.get_json()
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
    logger.debug("Received request to update title for chat_id: %s", chat_id)
    if not validate_chat_access(chat_id):
        return jsonify({"error": "Chat not found or access denied"}), 403

    data = request.get_json()
    title = bleach.clean(data.get("title", "").strip())
    if not title or len(title) > 100:
        return jsonify({"error": "Title is required and must be under 100 characters"}), 400

    try:
        Chat.update_title(chat_id, title)
        logger.info("Chat title updated for chat_id: %s", chat_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Error updating chat title: %s", str(e))
        return jsonify({"error": "Failed to update chat title"}), 500


##############################################################################
# 5) Stats route => GET /chat/stats/<chat_id>
##############################################################################

@chat_routes.route("/stats/<chat_id>", methods=["GET"])
@login_required
def get_chat_stats(chat_id: str) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Get chat statistics including token usage."""
    try:
        if not validate_chat_access(chat_id):
            return jsonify({"error": "Unauthorized access to chat"}), 403

        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            return jsonify({"error": "Model not found"}), 404

        token_limit = get_model_token_limit(model_obj)
        usage_stats = conversation_manager.get_usage_stats(chat_id) or {
            "total_tokens": 0,
            "token_breakdown": {"user": 0, "assistant": 0, "system": 0},
        }

        token_breakdown = usage_stats.get("token_breakdown", {})
        total_tokens = (
            token_breakdown.get("user", 0)
            + token_breakdown.get("assistant", 0)
            + token_breakdown.get("system", 0)
        )

        token_usage_percentage = (total_tokens / token_limit) * 100 if token_limit > 0 else 0

        logger.debug(
            "Token usage stats for chat %s: total=%d, limit=%d, percentage=%.2f%%",
            chat_id, total_tokens, token_limit, token_usage_percentage
        )
        logger.debug("Token breakdown for chat %s: %s", chat_id, token_breakdown)

        stats = {
            "total_tokens": total_tokens,
            "token_limit": token_limit,
            "token_usage_percentage": token_usage_percentage,
            "token_breakdown": token_breakdown,
            "model_limits": {"max_tokens": token_limit},
        }
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.error("Error getting chat stats: %s", e, exc_info=True)
        return jsonify({"error": "Failed to get chat statistics"}), 500


##############################################################################
# 6) Route for updating model => /chat/update_model
#    (Removed duplicated lines so it doesn't exit early.)
##############################################################################
@chat_routes.route("/update_model", methods=["POST"])
@login_required
def update_model() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Update the model for a chat with proper transaction handling."""
    data = request.get_json() or {}
    chat_id = data.get("chat_id") or session.get("chat_id")
    new_model_id = data.get("model_id")

    # Validate inputs
    if not chat_id or not new_model_id:
        return jsonify({"error": "Chat ID and Model ID are required."}), 400

    if not validate_chat_access(chat_id):
        return jsonify({"error": "Unauthorized access to chat"}), 403

    with db_session() as db:
        model = Model.get_by_id(new_model_id)
        if not model:
            return jsonify({"error": "Model not found"}), 404

        model_err = validate_model(model)
        if model_err:
            return jsonify({"error": model_err}), 400

        # Example: Check for "active streaming" to disallow changes
        active_stream = db.execute(
            text(
                """
                SELECT COUNT(*) FROM messages
                WHERE chat_id = :chat_id
                  AND metadata->>'streaming' = 'true'
                  AND timestamp >= NOW() - INTERVAL '1 minute'
                """
            ),
            {"chat_id": chat_id},
        ).scalar()

        if active_stream:
            return jsonify({"error": "Cannot switch models during active streaming"}), 409

        Chat.update_model_id(chat_id, new_model_id)
        db.commit()

    logger.info("Model updated to %s for chat %s", new_model_id, chat_id)
    return jsonify({"success": True})


##############################################################################
# Helper: Validate Chat Request
##############################################################################

def validate_chat_request(request_data) -> Dict[str, Any]:
    """Validate incoming chat request for CSRF, chat ID, etc."""
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
