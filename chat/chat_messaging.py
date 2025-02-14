# chat_messaging.py
"""
Unified Flask-based chat handling module that integrates with Azure OpenAI.
Provides both streaming and non-streaming responses, file uploads,
and URL scraping functionality.
"""

import json
import uuid
import bleach
import mistune
from datetime import datetime
from typing import Dict, List, Any, Generator, Optional, Union, Tuple

from flask import (
    request, jsonify, Response, session
)
from flask.wrappers import Response as FlaskResponse
from flask_login import login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import your local modules
from . import chat_routes
from extensions import csrf
from chat.chat_utilities import (
    process_uploaded_files,
    validate_chat_access,
    format_file_contents_for_o1,
    detect_urls,
    scrape_url,
    format_scraped_data
)
from models.chat import Chat
from models.model import Model
from models.uploaded_file import UploadedFile
from azure_search_client import AzureOpenAI
from conversation_manager import conversation_manager
from chat_api import get_azure_response

# Logging setup
from logging_config import get_logger
logger = get_logger(__name__)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
CHAT_RATE_LIMIT = "60 per minute"

# (Optional) Example: safe domain allowlist for URL scraping
SAFE_DOMAINS = ["example.com", "docs.python.org"]  # Adjust as needed

def server_side_format_markdown(raw_text: str) -> str:
    """
    Convert raw text to HTML using Mistune for server-side Markdown rendering.
    """
    markdown_processor = mistune.create_markdown(
        plugins=["url", "table"],
        escape=False
    )
    return str(markdown_processor(raw_text))


@chat_routes.route("/send", methods=["POST"])
@limiter.limit(CHAT_RATE_LIMIT)
@login_required
def handle_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Main endpoint to handle incoming chat messages with optional file uploads.
    Determines whether to stream or return a normal (non-streaming) response.
    """
    try:
        # -------------------------
        # Validate Chat Access
        # -------------------------
        chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id", "")
        if not isinstance(chat_id, str):
            chat_id = str(chat_id)

        if not chat_id:
            logger.warning("No chat ID provided")
            return jsonify({"error": "No chat ID provided"}), 400

        if not validate_chat_access(chat_id, current_user.id):
            logger.warning(f"Unauthorized access attempt: chat_id={chat_id}")
            return jsonify({"error": "Unauthorized access to chat"}), 403

        # --------------------------------
        # Retrieve Model and Config
        # --------------------------------
        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            logger.warning(f"No model configured for chat_id={chat_id}")
            return jsonify({"error": "No model configured"}), 400

        # --------------------------------
        # Gather Message and Files
        # --------------------------------
        files_data = []
        included_files = []
        if request.is_json:
            data = request.get_json()
            message = data.get("message", "").strip()

            # Handle file IDs in JSON
            if 'file_ids' in data:
                for file_id in data['file_ids']:
                    file_record = UploadedFile.get_by_id(file_id)
                    if isinstance(file_record, UploadedFile) and getattr(file_record, "text_content", None):
                        files_data.append({
                            'filename': file_record.filename,
                            'content': file_record.text_content
                        })
        else:
            # Handle form data
            message = request.form.get("message", "").strip()
            # Handle file uploads
            files_list = request.files.getlist("uploaded_files") or request.files.getlist("files[]")
            if files_list and any(f.filename for f in files_list):
                processed_files = process_uploaded_files(files_list)
                included_files, excluded_files, total_tokens, files_data = processed_files

                if excluded_files:
                    logger.info(f"Some files could not be processed: {excluded_files}")
                    return jsonify({
                        "error": "Some files could not be processed",
                        "details": excluded_files
                    }), 400

        if not message and not files_data:
            logger.warning("No message or files provided")
            return jsonify({"error": "No message or files provided"}), 400

        # ------------------------------------------
        # Combine and Sanitize Prompt with File Data
        # ------------------------------------------
        if model_obj.model_type.lower() in ['o1', 'o1-mini', 'o1-preview']:
            combined_message = format_file_contents_for_o1(files_data, message)
        else:
            combined_message = message
            if files_data:
                # Attach file contents to the prompt
                combined_message += "\n\nAttached files:\n" + "\n".join(
                    f"[{fc['filename']}]\n{fc['content']}"
                    for fc in files_data
                )

        combined_message = bleach.clean(combined_message)

        # -------------------------------------
        # URL Detection, (Optional) Domain Check
        # -------------------------------------
        try:
            urls = detect_urls(combined_message)
            scraped_content = []

            for url in urls:
                # (Optional) Check domain allowlist/size limit:
                # e.g., skip if domain is not in SAFE_DOMAINS
                # or if response is too large.
                # This is a minimal example:
                # from urllib.parse import urlparse
                # domain = urlparse(url).netloc
                # if domain not in SAFE_DOMAINS:
                #     logger.warning(f"Skipping URL from unauthorized domain: {domain}")
                #     continue

                # Attempt to scrape the URL
                try:
                    raw_html = scrape_url(url)
                    # You can limit the size or scanning time
                    if raw_html:
                        formatted_text = format_scraped_data(raw_html)
                        if formatted_text:
                            scraped_content.append(
                                f"\n\n***Scraped Content from {url}***\n{formatted_text}"
                            )
                except Exception as e:
                    logger.error(f"Error scraping URL {url}: {str(e)}", exc_info=True)
                    continue

            if scraped_content:
                combined_message += "\n".join(scraped_content)

        except Exception as e:
            logger.error(f"Error in URL detection/scraping: {str(e)}", exc_info=True)

        # -------------------------------------
        # Add User Message to Conversation
        # -------------------------------------
        _ = conversation_manager.add_message(
            chat_id=chat_id,
            role="user",
            content=combined_message,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
            timestamp=datetime.utcnow()
        )

        # Fetch updated conversation context
        history = conversation_manager.get_context(
            chat_id,
            include_system=not model_obj.requires_o1_handling
        )

        # Check if streaming is requested and supported
        use_streaming = (
            model_obj.supports_streaming
            and not model_obj.requires_o1_handling
            and request.args.get("stream", "false").lower() == "true"
        )

        if use_streaming:
            logger.debug(f"Streaming response is enabled for chat_id={chat_id}")
            return stream_response(chat_id, history, model_obj)
        else:
            logger.debug(f"Normal (non-streaming) response for chat_id={chat_id}")
            return normal_response(chat_id, history, model_obj, included_files)

    except Exception as e:
        logger.error("Chat handling error: %s", str(e), exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


def stream_response(
    chat_id: str,
    history: List[Dict[str, Any]],
    model_obj: Model
) -> FlaskResponse:
    """
    Handle streaming responses using AzureOpenAI via Server-Sent Events (SSE).
    """

    def generate() -> Generator[str, None, None]:
        """
        Generator function that yields response chunks as SSE events.
        """
        try:
            # Create AzureOpenAI client
            client = AzureOpenAI(
                azure_endpoint=model_obj.api_endpoint,
                api_key=model_obj.api_key,
                api_version=model_obj.api_version,
            )

            # Build request parameters
            completion_params = {
                "model": model_obj.deployment_name,
                "messages": history,
                "max_completion_tokens": model_obj.max_completion_tokens,
                "stream": True
            }

            # If model type is in the O-series or similar
            if model_obj.model_type and model_obj.model_type.lower() in [
                "o3-mini", "o1", "o1-mini", "o1-preview"
            ]:
                completion_params["temperature"] = 1.0
            else:
                completion_params["temperature"] = model_obj.temperature

            logger.debug(
                f"Starting streaming call for chat_id={chat_id}, model_type={model_obj.model_type}"
            )

            # Stream the response chunks
            response = client.chat.completions.create(**completion_params)
            for chunk in response:
                # If chunk is just a string or not a valid chunk object, skip
                if isinstance(chunk, str) or not hasattr(chunk, "choices"):
                    continue

                choices = getattr(chunk, "choices", [])
                if not choices:
                    continue

                choice = choices[0]
                # The chunk could be a dict or an object
                if isinstance(choice, dict):
                    delta = choice.get("delta")
                else:
                    delta = getattr(choice, "delta", None)

                if not delta:
                    continue

                # Extract content
                if isinstance(delta, dict):
                    content = delta.get("content")
                else:
                    content = getattr(delta, "content", None)

                # Yield SSE event if content is found
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"

            # Signal completion
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {str(e)}", exc_info=True)
            # Return an SSE error message
            yield f"data: {json.dumps({'error': f'API Error: {str(e)}'})}\n\n"

    return Response(
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
    model_obj: Model,
    included_files: List[Any]
) -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Handle non-streaming responses with AzureOpenAI or O-series models.
    Returns a single JSON response with the model's entire output.
    """
    try:
        if not model_obj:
            logger.warning("Normal response attempted without model_obj.")
            return jsonify({"error": "No model configured"}), 400

        logger.debug(
            f"Preparing normal response for chat_id={chat_id}, model_type={model_obj.model_type}"
        )

        model_type = (model_obj.model_type or "").lower()
        is_o_series = model_type in ["o1", "o1-mini", "o1-preview", "o3-mini"]
        max_tokens = getattr(model_obj, "max_completion_tokens", 100000)

        # Cap token limits for certain O-series models
        if is_o_series:
            token_limits = {
                "o3-mini": 75000,
                "o1": 100000,
                "o1-mini": 50000,
                "o1-preview": 32768
            }
            model_limit = token_limits.get(model_type, 32768)
            max_tokens = min(max_tokens, model_limit)

        # Prepare params for Azure
        api_params = {
            "messages": history,
            "deployment_name": model_obj.deployment_name,
            "max_completion_tokens": max_tokens,
            "api_endpoint": model_obj.api_endpoint,
            "api_key": model_obj.api_key,
            "api_version": model_obj.api_version,
            "model_type": model_obj.model_type,
            "requires_o1_handling": model_obj.requires_o1_handling,
            "stream": False,
        }

        if is_o_series:
            api_params["temperature"] = 1.0
            # Example: You might set "reasoning_effort" or other custom parameters
            # for O-series models if your API supports them.

        # Get model response (non-streaming)
        response = get_azure_response(**api_params)
        logger.debug("Raw model response received from get_azure_response()")

        # Extract content from the response
        content: Optional[str] = None
        if isinstance(response, dict):
            # Dictionary style
            choices = response.get("choices", [])
            if choices:
                choice = choices[0]
                message_obj = choice.get("message", {})
                if isinstance(message_obj, dict):
                    content = message_obj.get("content")
        elif not isinstance(response, (str, Generator)) and hasattr(response, "choices") and response.choices:
            # Object style
            choice = response.choices[0]
            if hasattr(choice, "message") and choice.message is not None:
                content = getattr(choice.message, "content", None)

        # Fallback if no content is returned
        if not content:
            if model_obj.requires_o1_handling:
                content = (
                    "[No response generated. The model may need more context "
                    "or a different prompt format.]"
                )
            else:
                content = "[No response from model. Please try again or contact support.]"

        # Convert to HTML for front-end rendering
        content_html = server_side_format_markdown(content)

        # Save the assistant message into conversation history
        conversation_manager.add_message(
            chat_id=chat_id,
            role="assistant",
            content=content,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
            timestamp=datetime.utcnow()
        )  # type: ignore

        # Prepare file metadata for the response
        saved_files = []
        if included_files:
            saved_files = [{
                "id": str(uuid.uuid4()),
                "filename": f.filename,
                "size": f.size,
                "mime_type": f.mime_type,
                "uploaded_at": datetime.utcnow().isoformat()
            } for f in included_files]

        return jsonify({
            "success": True,
            "saved_files": saved_files,
            "message": {
                "role": "assistant",
                "content": content,
                "content_html": content_html,
                "id": str(uuid.uuid4()),
            }
        })

    except Exception as e:
        logger.error("Normal response error: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_routes.route("/send_stream", methods=["POST"])
@login_required
@limiter.limit("60 per minute")
def handle_chat_stream() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Dedicated endpoint for streaming chat messages (SSE).
    Useful if you want a separate route for streaming
    rather than the combined logic in /send.
    """
    try:
        chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id", "")
        if not isinstance(chat_id, str):
            chat_id = str(chat_id)

        if not chat_id:
            return jsonify({"error": "No chat ID provided"}), 400

        if not validate_chat_access(chat_id, current_user.id):
            return jsonify({"error": "Unauthorized access to chat"}), 403

        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            return jsonify({"error": "No model configured"}), 400

        if not model_obj.supports_streaming or model_obj.requires_o1_handling:
            return jsonify({"error": "Model does not support streaming"}), 400

        # Retrieve conversation context
        history = conversation_manager.get_context(chat_id)
        return stream_response(chat_id, history, model_obj)

    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@chat_routes.after_request
def add_cors_headers(response: FlaskResponse) -> FlaskResponse:
    """
    Add required CORS headers for streaming support, and disable nginx buffering.
    """
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Chat-ID, api-key, X-CSRFToken, X-Requested-With"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Accel-Buffering"] = "no"  # Disable buffering for nginx
    return response
