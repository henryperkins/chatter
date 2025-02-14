"""
Message handling and streaming functionality for chat system.
Handles processing of chat messages, file uploads, and response generation.
"""

import json
import uuid
import bleach
import mistune
from datetime import datetime
from typing import Dict, List, Any, Generator, Optional, Union, Tuple

from . import chat_routes
from flask import (
    request, jsonify, Response,
    session
)
from flask.wrappers import Response as FlaskResponse
from flask_login import login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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

# Logging setup
from logging_config import get_logger
logger = get_logger(__name__)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
CHAT_RATE_LIMIT = "60 per minute"

def server_side_format_markdown(raw_text: str) -> str:
    """Convert raw text to HTML using Mistune server-side rendering."""
    markdown_processor = mistune.create_markdown(
        plugins=["url", "table"],
        escape=False
    )
    return str(markdown_processor(raw_text))

@limiter.limit(CHAT_RATE_LIMIT)
@login_required
def handle_chat() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """
    Handle incoming chat messages with optional file uploads.
    Supports both streaming and non-streaming responses.
    """
    try:
        # Get chat ID and validate access
        chat_id = request.headers.get("X-Chat-ID") or session.get("chat_id", "")
        if not isinstance(chat_id, str):
            chat_id = str(chat_id)

        if not chat_id:
            return jsonify({"error": "No chat ID provided"}), 400

        if not validate_chat_access(chat_id, current_user.id):
            return jsonify({"error": "Unauthorized access to chat"}), 403

        # Get model configuration
        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            return jsonify({"error": "No model configured"}), 400

        # Initialize variables for files and message
        files_data = []
        included_files = []
        
        # Handle JSON or form data
        if request.is_json:
            data = request.get_json()
            message = data.get("message", "").strip()
            
            # Handle file IDs if provided in JSON
            if 'file_ids' in data:
                for file_id in data['file_ids']:
                    file_record = UploadedFile.get_by_id(file_id)
                    if file_record and file_record.text_content:
                        files_data.append({
                            'filename': file_record.filename,
                            'content': file_record.text_content
                        })
        else:
            message = request.form.get("message", "").strip()
            
            # Process file uploads if any
            files_list = request.files.getlist("uploaded_files") or request.files.getlist("files[]")
            if files_list and any(f.filename for f in files_list):
                processed_files = process_uploaded_files(files_list)
                included_files, excluded_files, total_tokens, files_data = processed_files
                
                if excluded_files:
                    return jsonify({
                        "error": "Some files could not be processed",
                        "details": excluded_files
                    }), 400

        if not message and not files_data:
            return jsonify({"error": "No message or files provided"}), 400

        # Combine message and file contents based on model type
        if model_obj.model_type.lower() in ['o1', 'o1-mini', 'o1-preview']:
            combined_message = format_file_contents_for_o1(files_data, message)
        else:
            combined_message = message
            if files_data:
                combined_message += "\n\nAttached files:\n" + "\n".join(
                    f"[{fc['filename']}]\n{fc['content']}" 
                    for fc in files_data
                )

        # Sanitize user content
        combined_message = bleach.clean(combined_message)

        # Handle URL detection and scraping
        try:
            urls = detect_urls(combined_message)
            scraped_content = []
            
            for url in urls:
                try:
                    raw_html = scrape_url(url)
                    if raw_html:
                        formatted_text = format_scraped_data(raw_html)
                        if formatted_text:
                            scraped_content.append(
                                f"\n\n***Scraped Content from {url}***\n{formatted_text}"
                            )
                except Exception as e:
                    logger.error(f"Error scraping URL {url}: {str(e)}")
                    continue
            
            if scraped_content:
                combined_message += "\n".join(scraped_content)

        except Exception as e:
            logger.error(f"Error in URL detection/scraping: {str(e)}")
            # Continue with original message if scraping fails

        # Add user message to conversation history
        conversation_manager.add_message(
            chat_id=chat_id,
            role="user",
            content=combined_message,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling
        )

        # Get updated conversation context
        history = conversation_manager.get_context(
            chat_id,
            include_system=not model_obj.requires_o1_handling
        )

        # Determine if streaming should be used
        use_streaming = (
            model_obj.supports_streaming
            and not model_obj.requires_o1_handling
            and request.args.get("stream", "false").lower() == "true"
        )

        if use_streaming:
            return stream_response(chat_id, history, model_obj)
        else:
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
    Handle streaming responses using AzureOpenAI.
    Generates server-sent events for real-time message streaming.
    """
    logger.debug(
        "Starting stream_response with model_id=%d, model_type=%s",
        model_obj.id,
        model_obj.model_type
    )

    def generate() -> Generator[str, None, None]:
        """Generate streaming response chunks."""
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

            # Add temperature for different model types
            if model_obj.model_type and model_obj.model_type.lower() in [
                "o3-mini", "o1", "o1-mini", "o1-preview"
            ]:
                completion_params["temperature"] = 1.0
            else:
                completion_params["temperature"] = model_obj.temperature

            response = client.chat.completions.create(**completion_params)
            logger.debug("Streaming response initiated")

            for chunk in response:
                # Handle string chunks directly
                if isinstance(chunk, str):
                    yield chunk
                    continue
                
                # Process response chunks
                choices = getattr(chunk, "choices", [])
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
    Handle normal (non-streaming) response while respecting model constraints.
    Returns a complete response with processed content and file metadata.
    """
    try:
        if not model_obj:
            return jsonify({"error": "No model configured"}), 400

        logger.debug(
            "Starting normal_response with model_id=%d, model_type=%s",
            model_obj.id,
            model_obj.model_type
        )

        # Determine model type and constraints
        model_type = model_obj.model_type or ""
        is_o_series = model_type.lower() in [
            "o1", "o1-mini", "o1-preview", "o3-mini"
        ]

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
            max_tokens = min(max_tokens, model_limit)

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
            if model_type.lower() in ["o3-mini", "o1"]:
                api_params["reasoning_effort"] = "medium"

        # Get response from Azure
        from chat_api import get_azure_response
        response = get_azure_response(**api_params)
        logger.debug("Raw model response received")

        # Extract content with safer attribute checks
        content: Optional[str] = None

        # Handle dict response
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    message_obj = choice.get("message", {})
                    if isinstance(message_obj, dict):
                        content = message_obj.get("content")

        # Handle object response
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

        logger.info(
            "Normal response content length: %d",
            len(content) if content else 0
        )

        # Convert raw content to HTML
        content_html = server_side_format_markdown(content)

        # Save the assistant message
        conversation_manager.add_message(
            chat_id=chat_id,
            role="assistant",
            content=content,
            model_max_tokens=model_obj.max_tokens,
            requires_o1_handling=model_obj.requires_o1_handling,
        )

        # Prepare file metadata
        saved_files = [{
            "id": str(uuid.uuid4()),
            "filename": f.filename,
            "size": f.size,
            "mime_type": f.mime_type,
            "uploaded_at": datetime.utcnow().isoformat()
        } for f in included_files] if included_files else []

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
@csrf.protect()
def handle_chat_stream() -> Union[FlaskResponse, Tuple[FlaskResponse, int]]:
    """Dedicated endpoint for handling streaming chat messages."""
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

        history = conversation_manager.get_context(chat_id)
        return stream_response(chat_id, history, model_obj)

    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# CORS headers for streaming support
@chat_routes.after_request
def add_cors_headers(response: FlaskResponse) -> FlaskResponse:
    """Add required CORS headers for streaming support."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Chat-ID, api-key, X-CSRFToken, X-Requested-With"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Accel-Buffering"] = "no"  # Disable buffering for nginx
    return response
