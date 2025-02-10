import uuid
import os
import smtplib
import logging
from typing import List, Dict, Tuple, Any
from werkzeug.utils import secure_filename as werkzeug_secure_filename
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import jsonify
from token_utils import count_tokens, truncate_content, get_encoding
from context_manager import ContextManager, ContextMonitor

# Constants
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")  # Default model name
MAX_FILE_CONTENT_LENGTH = int(os.getenv("MAX_FILE_CONTENT_LENGTH", "8000"))  # Characters

# Initialize tokenizer
encoding = get_encoding()

# Cache for encodings to improve performance
_encoding_cache = {}

def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it is safe for storage.

    Args:
        filename (str): The original filename.

    Returns:
        str: A sanitized version of the filename.
    """
    return werkzeug_secure_filename(filename).replace(' ', '_')

def generate_new_chat_id() -> str:
    """
    Generate a new unique chat ID.

    Returns:
        str: A UUID-based unique chat ID.
    """
    return str(uuid.uuid4())

def extract_context_from_conversation(
    messages: List[Dict[str, str]], latest_response: str, max_tokens: int = 4000
) -> str:
    """
    Extract key context from the conversation.

    Args:
        messages (List[Dict[str, str]]): List of message dictionaries, each containing 'role' and 'content' keys.
        latest_response (str): The latest response from the model.
        max_tokens (int): The maximum number of tokens allowed in the context.

    Returns:
        str: A string containing the extracted context, limited to the specified token count.
    """
    context_parts: List[str] = []

    # Consider last 10 messages for context
    context_parts.extend(
        f"{msg['role']}: {msg['content']}"
        for msg in messages[-10:]
        if msg["role"] in ["assistant", "user"]
    )
    # Add the latest response
    context_parts.append(f"assistant: {latest_response}")

    # Join all parts with newlines
    context = "\n".join(context_parts)

    # Truncate context to the specified token limit
    tokens = encoding.encode(context)
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens]
        context = encoding.decode(truncated_tokens)
        context += "\n\n[Note: Context truncated due to token limit.]"

    return context

def truncate_message(message: str, max_tokens: int = MAX_FILE_CONTENT_LENGTH) -> str:
    """
    Truncate a message to a specified number of tokens.

    Args:
        message (str): The message to truncate.
        max_tokens (int): The maximum number of tokens allowed.

    Returns:
        str: The truncated message.
    """
    return truncate_content(message, max_tokens, "[Note: Input truncated due to token limit.]")

def allowed_file(filename: str) -> bool:
    """
    Check if the file has an allowed extension.

    Args:
        filename (str): The filename to check.

    Returns:
        bool: True if the file extension is allowed, False otherwise.
    """
    allowed_extensions = {".txt", ".md", ".py", ".js", ".html", ".css", ".json", ".csv"}
    return os.path.splitext(filename)[1].lower() in allowed_extensions

def count_file_tokens(content: str) -> int:
    """Count tokens for file content with additional overhead."""
    base_tokens = count_tokens(content)
    # Add overhead for file metadata and structure
    return base_tokens + 10


# Initialize context management
context_manager = ContextManager(model_max_tokens=int(os.getenv("MODEL_MAX_TOKENS", "8000")))
context_monitor = ContextMonitor()

def process_file(file) -> Tuple[str, str, int]:
    """
    Process an uploaded file by validating, truncating, and reading its content.
    Uses context management for intelligent truncation and token optimization.

    Args:
        file: The uploaded file object.

    Returns:
        Tuple[str, str, int]: A tuple containing the filename, truncated content, and token count.

    Raises:
        ValueError: If the file is invalid or cannot be processed.
    """
    if not file.filename:
        raise ValueError("Empty filename provided")
        
    filename = secure_filename(file.filename)
    if not filename:
        raise ValueError("Invalid filename")
        
    mime_type = file.mimetype
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    if not ext:
        raise ValueError("File must have an extension")

    # Check file size
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    max_file_size = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10 MB
    if file_length > max_file_size:
        raise ValueError(f"File too large: {filename} exceeds the {max_file_size} byte limit.")

    # Special handling for text-based files that might be detected as octet-stream
    if mime_type == 'application/octet-stream':
        try:
            file.seek(0)
            # Try to read and decode a sample to verify it's text
            file.read(1024).decode('utf-8')
            file.seek(0)
            if ext in ['md', 'txt', 'json', 'py', 'js', 'css', 'html', 'csv']:
                mime_type = f'text/{ext}' if ext != 'md' else 'text/markdown'
        except (UnicodeDecodeError, Exception):
            raise ValueError(f"Unable to process file as text: {filename}")

    # Process text-based files with context management
    if mime_type.startswith('text/') or mime_type in ['application/json']:
        try:
            file_content = file.read().decode('utf-8')

            # Use context monitor for intelligent file content compression
            truncated_content = context_monitor.compress_file_content(
                file_content,
                MAX_FILE_CONTENT_LENGTH
            )

            # Track token usage
            token_count = count_file_tokens(truncated_content)
            context_monitor.track_token_usage(token_count)

            # Cache the processed content
            cache_key = hash((filename, len(file_content)))
            context_manager.context_cache[cache_key] = truncated_content

            # Check if content was truncated
            if len(truncated_content) < len(file_content):
                logger.info(f"File {filename} was truncated from {len(file_content)} to {len(truncated_content)} characters")

            return filename, truncated_content, token_count
        except UnicodeDecodeError as e:
            raise ValueError(f"Failed to decode file {filename}: {e}")
    else:
        raise ValueError(f"Unsupported file type ({mime_type}): {filename}")

def generate_chat_title(conversation_text: str) -> str:
    """
    Generate a chat title based on the first 5 messages.

    Args:
        conversation_text (str): The conversation text.

    Returns:
        str: A generated chat title.
    """
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
        top_words = sorted(word_counts.keys(), key=lambda x: word_counts.get(x, 0), reverse=True)[:2]

        # Create title from top words or fallback to default
        if top_words:
            return " ".join([word.capitalize() for word in top_words])
        return "New Chat"

def send_email(subject: str, recipient_email: str, text_content: str, html_content: str) -> None:
    """Send an email with the specified subject and content."""
    sender_email = os.getenv("EMAIL_SENDER", "no-reply@example.com")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.example.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME", "username")
    smtp_password = os.getenv("SMTP_PASSWORD", "password")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = recipient_email

    message.attach(MIMEText(text_content, "plain"))
    message.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, recipient_email, message.as_string())
    except Exception as e:
        raise Exception(f"Failed to send email: {e}")

def send_reset_email(recipient_email: str, reset_link: str) -> None:
    """Send a password reset email to the specified recipient."""
    subject = "Password Reset Request"
    text = f"Please click the following link to reset your password: {reset_link}"
    html = f"<html><body><p>{text}</p><a href='{reset_link}'>{reset_link}</a></body></html>"
    send_email(subject, recipient_email, text, html)

def validate_password_strength(password: str) -> List[str]:
    """
    Validate password strength and return a list of errors.
    """
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one number.")
    if not any(c in '!@#$%^&*(),.?":{}|<>' for c in password):
        errors.append("Password must contain at least one special character.")
    return errors


logger = logging.getLogger(__name__)

def handle_error(error, message="An error occurred"):
    """
    Centralized error handling utility.
    """
    logger.error(f"{message}: {error}")
    return jsonify({"success": False, "error": str(error)}), 500

def send_verification_email(recipient_email: str, verification_token: str) -> None:
    """Send an email to the user with a verification link."""
    subject = "Email Verification"
    verification_url = f"{os.getenv('APP_URL', 'http://localhost:5000')}/auth/verify_email/{verification_token}"
    text = f"Please click the following link to verify your email: {verification_url}"
    html = f"<html><body><p>{text}</p><a href='{verification_url}'>{verification_url}</a></body></html>"
    send_email(subject, recipient_email, text, html)

def process_uploaded_files(files: List[Any]) -> Tuple[List[str], List[Dict[str, str]], int, List[Dict[str, str]]]:
    """
    Process multiple uploaded files, validating and processing each one.

    Args:
        files: List of file objects from request.files

    Returns:
        Tuple containing:
        - List of included filenames
        - List of excluded files with error messages
        - Total token count
        - List of processed file contents with filenames

    Raises:
        ValueError: If no valid files are provided or if processing fails
    """
    if not files:
        raise ValueError("No files provided")

    included_files = []
    excluded_files = []
    total_tokens = 0
    file_contents = []

    for file in files:
        try:
            filename, content, token_count = process_file(file)
            included_files.append(filename)
            total_tokens += token_count
            file_contents.append({
                "filename": filename,
                "content": content
            })
        except ValueError as e:
            excluded_files.append({"filename": file.filename, "error": str(e)})
            logger.warning(f"File excluded: {file.filename} - {str(e)}")

    return included_files, excluded_files, total_tokens, file_contents
