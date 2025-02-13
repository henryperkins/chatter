"""
Helper functions and utilities for chat functionality.
Handles file operations, validation, and common utilities.
"""

import os
import uuid
import tiktoken
from typing import Tuple, List, Dict, Any, Optional
from werkzeug.datastructures import FileStorage

from logging_config import get_logger
logger = get_logger(__name__)

# Constants
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", default=str(10 * 1024 * 1024)))  # 10 MB
MAX_TOTAL_FILE_SIZE = int(os.getenv("MAX_TOTAL_FILE_SIZE", default=str(50 * 1024 * 1024)))  # 50 MB
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx", "md"}
DEFAULT_MODEL = "gpt-4"
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", default="8192"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", default="128000"))

def init_upload_folder() -> None:
    """Initialize the secure upload folder if it doesn't exist."""
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)

def get_token_encoder(model_name: str = DEFAULT_MODEL) -> tiktoken.Encoding:
    """Get the appropriate token encoder for the model."""
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        logger.warning(f"Model '{model_name}' not found. Using 'cl100k_base'.")
        return tiktoken.get_encoding("cl100k_base")

def validate_chat_access(chat_id: str, user_id: int, user_role: str = "user") -> bool:
    """
    Check if the current user can access the given chat.
    
    Args:
        chat_id: The ID of the chat to check
        user_id: The ID of the user attempting access
        user_role: The role of the user (default: "user")
        
    Returns:
        bool: True if access is allowed, False otherwise
    """
    if not chat_id or not isinstance(chat_id, str):
        return False
    from models.chat import Chat
    return Chat.can_access_chat(chat_id, user_id, user_role)

def process_uploaded_files(
    files: List[FileStorage]
) -> Tuple[List[Dict[str, Any]], List[str], int, List[Dict[str, str]]]:
    """
    Process and validate uploaded files.
    
    Returns:
        Tuple containing:
        - List of included files with metadata
        - List of excluded files with reasons
        - Total token count
        - List of file contents
    """
    included_files = []
    excluded_files = []
    total_tokens = 0
    file_contents = []
    
    current_total_size = 0
    encoder = get_token_encoder()

    for file in files:
        if not file or not file.filename:
            continue

        try:
            # Basic validation
            if not allowed_file(file.filename):
                excluded_files.append(f"{file.filename}: Unsupported file type")
                continue

            # Size validation
            file_size = os.fstat(file.fileno()).st_size
            if file_size > MAX_FILE_SIZE:
                excluded_files.append(f"{file.filename}: File too large")
                continue

            if current_total_size + file_size > MAX_TOTAL_FILE_SIZE:
                excluded_files.append(f"{file.filename}: Would exceed total size limit")
                continue

            # Read and process content
            content = file.read().decode('utf-8')
            tokens = len(encoder.encode(content))
            
            if tokens > MAX_INPUT_TOKENS:
                excluded_files.append(f"{file.filename}: Content too long")
                continue

            # Update counters
            current_total_size += file_size
            total_tokens += tokens

            # Store file information
            included_files.append({
                'filename': file.filename,
                'size': file_size,
                'tokens': tokens,
                'mime_type': file.content_type or 'text/plain'
            })
            
            file_contents.append({
                'filename': file.filename,
                'content': content
            })

        except UnicodeDecodeError:
            excluded_files.append(f"{file.filename}: Not a valid text file")
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}")
            excluded_files.append(f"{file.filename}: Processing error")

    return included_files, excluded_files, total_tokens, file_contents

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_new_chat_id() -> str:
    """Generate a new unique chat ID."""
    return str(uuid.uuid4())

def format_file_contents_for_o1(
    file_contents: List[Dict[str, str]],
    message: str
) -> str:
    """
    Format file contents and message for O1 model compatibility.
    
    Args:
        file_contents: List of dictionaries containing filename and content
        message: The user's message
        
    Returns:
        str: Formatted content string
    """
    formatted_content = message + "\n\n" if message else ""
    
    if file_contents:
        formatted_content += "Documents:\n\n"
        for doc in file_contents:
            formatted_content += f"[{doc['filename']}]\n{doc['content']}\n\n"
    
    return formatted_content.strip()

def truncate_content(
    text: str,
    max_tokens: int,
    truncation_note: str = "\n\n[Content truncated due to length...]"
) -> str:
    """
    Truncate text to stay within token limit.
    
    Args:
        text: Text to truncate
        max_tokens: Maximum allowed tokens
        truncation_note: Note to append if truncated
        
    Returns:
        str: Truncated text with note if needed
    """
    try:
        encoder = get_token_encoder(DEFAULT_MODEL)
        tokens = encoder.encode(text)
        note_tokens = encoder.encode(truncation_note)
        allowed = max_tokens - len(note_tokens)
        
        if len(tokens) <= max_tokens:
            return text
            
        truncated_tokens = tokens[:allowed]
        truncated_text = encoder.decode(truncated_tokens)
        return truncated_text + truncation_note
        
    except Exception as e:
        logger.error(f"Error truncating content: {str(e)}")
        return text[:max_tokens * 4] + truncation_note  # Rough character estimate

def get_model_token_limit(model_obj: Any) -> int:
    """
    Safely retrieve the model's max_tokens, with fallback.
    
    Args:
        model_obj: Model object with potential max_tokens attribute
        
    Returns:
        int: Maximum token limit (defaults to 16384)
    """
    max_tokens = getattr(model_obj, "max_tokens", None)
    if isinstance(max_tokens, int) and max_tokens > 0:
        return max_tokens
    return 16384

def validate_model(model: Optional[Any]) -> Optional[str]:
    """
    Validate a model's configuration.
    
    Args:
        model: Model object to validate
        
    Returns:
        Optional[str]: Error message if invalid, None if valid
    """
    if not model:
        return "No model configured for this chat."

    try:
        # Validate max_completion_tokens
        max_completion_tokens = getattr(model, "max_completion_tokens", None)
        if max_completion_tokens is None:
            return "max_completion_tokens is required"

        try:
            max_completion_tokens = int(max_completion_tokens)
            if not (1 <= max_completion_tokens <= 16384):
                return "max_completion_tokens must be between 1 and 16384"
        except (TypeError, ValueError):
            return "max_completion_tokens must be a valid integer"

        # Validate provider configuration
        provider_id = getattr(model, "provider_id", None)
        from models.provider import Provider
        provider = Provider.get_by_id(provider_id) if provider_id else None
        if not provider:
            return "Invalid provider configuration"

        # Check provider capabilities
        provider_max = provider.capabilities.get("max_tokens", 16384)
        model_type = getattr(model, "model_type", "")
        if not model_type:
            return "model_type is required"

        # Special handling for O1 preview models
        requires_o1 = getattr(model, "requires_o1_handling", False)
        is_o1_preview = model_type.lower() == "o1-preview" and requires_o1

        if is_o1_preview and max_completion_tokens > 8300:
            return "o1-preview models are limited to 8300 max_completion_tokens"

        return None

    except Exception as e:
        logger.error(f"Model validation error: {str(e)}")
        return f"Invalid model configuration: {str(e)}"

def detect_urls(text: str) -> List[str]:
    """
    Extract URLs from text using regex.
    
    Args:
        text: Text to search for URLs
        
    Returns:
        List[str]: List of found URLs
    """
    import re
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

def scrape_url(url: str) -> Optional[str]:
    """
    Safely scrape content from a URL.
    
    Args:
        url: URL to scrape
        
    Returns:
        Optional[str]: Scraped HTML content or None if failed
    """
    try:
        import requests
        from urllib.parse import urlparse
        
        # Basic URL validation
        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            return None
            
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
        
    except Exception as e:
        logger.error(f"Error scraping URL {url}: {str(e)}")
        return None

def format_scraped_data(html_content: str) -> Optional[str]:
    """
    Extract and format readable content from HTML.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Optional[str]: Formatted text content or None if failed
    """
    try:
        from bs4 import BeautifulSoup
        import html2text
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for element in soup(["script", "style"]):
            element.decompose()
            
        # Convert to markdown-style text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        text = h.handle(str(soup))
        
        # Clean up the text
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
        
    except Exception as e:
        logger.error(f"Error formatting scraped content: {str(e)}")
        return None

def validate_chat_request(request_data: Any) -> Dict[str, Any]:
    """
    Validate incoming chat request data.
    
    Args:
        request_data: Request data to validate
        
    Returns:
        Dict containing validation results
    """
    try:
        if not request_data.form:
            return {"valid": False, "error": "Missing form data"}

        chat_id = request_data.headers.get("X-Chat-ID") or session.get("chat_id")
        if not chat_id:
            return {"valid": False, "error": "Chat ID not found"}

        if not validate_chat_access(chat_id, current_user.id):
            return {"valid": False, "error": "Unauthorized access to chat"}

        return {"valid": True, "chat_id": chat_id}

    except Exception as e:
        logger.error(f"Request validation error: {str(e)}", exc_info=True)
        return {"valid": False, "error": "Request validation failed"}