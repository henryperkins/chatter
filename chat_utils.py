import uuid
import os
import smtplib
import logging
import hashlib
from typing import List, Dict, Tuple, Any
from werkzeug.utils import secure_filename as werkzeug_secure_filename
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import jsonify, current_app
import tiktoken
from token_utils import count_tokens, truncate_content, get_encoding
from context_manager import ContextManager, ContextMonitor

# File processing constants
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", "32000"))  # Default to 32k tokens

def scan_file(content: bytes) -> bool:
    """Stub virus scanning - integrate actual scanner here"""
    # Implement actual virus scanning integration
    return True  # Temporarily allow all files

def extract_text_from_file(file, mime_type: str) -> str:
    """
    Extract text content from non-text files using appropriate libraries.
    
    Args:
        file: File object to process
        mime_type: Detected MIME type of the file
        
    Returns:
        Extracted text content as string
    """
    try:
        file.seek(0)
        
        if mime_type == 'application/pdf':
            try:
                from pypdf import PdfReader
                reader = PdfReader(file)
                text = []
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text.append(extracted)
                return "\n\n".join(text)
            except ImportError:
                raise ValueError("PDF processing requires pypdf package")
            
        elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                          'application/msword']:
            try:
                from docx import Document
                doc = Document(file)
                text = []
                
                # Extract headers
                for para in doc.paragraphs:
                    if para.style.name.startswith('Heading'):
                        text.append(f"\n# {para.text}\n")
                    elif para.text.strip():
                        text.append(para.text)
                
                # Extract tables
                for table in doc.tables:
                    text.append("\nTable contents:")
                    for row in table.rows:
                        text.append(" | ".join(cell.text for cell in row.cells))
                
                return "\n".join(text)
            except ImportError:
                raise ValueError("DOCX processing requires python-docx package")
            
        else:
            raise ValueError(f"Unsupported file type for text extraction: {mime_type}")
            
    except ImportError as e:
        raise ValueError(f"Required library not installed for {mime_type} processing: {e}")
    except Exception as e:
        raise ValueError(f"Failed to extract text from {file.filename}: {e}")
    finally:
        file.seek(0)

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
    allowed_extensions = {".txt", ".md", ".html", ".py", ".pdf", ".docx", ".pptx"}
    return os.path.splitext(filename)[1].lower() in allowed_extensions

def count_file_tokens(content: str) -> int:
    """
    Count tokens for file content using tiktoken consistently.
    Adds small overhead for metadata/structure.
    """
    from token_utils import count_tokens
    try:
        # Use tiktoken for accurate counting
        base_tokens = count_tokens(content)
        # Add small overhead for metadata
        return base_tokens + 10
    except Exception as e:
        logger.error(f"Token counting failed: {e}")
        # Fallback only if tiktoken fails
        return len(content.split()) + 10


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

    # Extract text content based on mime type
    if mime_type in ['application/pdf', 'application/msword',
                   'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        try:
            file.seek(0)
            extracted_text = extract_text_from_file(file, mime_type)
        except ValueError as e:
            current_app.logger.error(f"Extraction failed for {filename}: {e}")
            extracted_text = ""
    else:
        # For text/* or fallback if we suspect it's textual
        file.seek(0)
        try:
            extracted_text = file.read().decode('utf-8')
        except UnicodeDecodeError:
            extracted_text = ""

    # Check file size
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    max_file_size = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10 MB
    if file_length > max_file_size:
        raise ValueError(f"File too large: {filename} exceeds the {max_file_size} byte limit.")

    # Handle different file types based on MIME type
    if mime_type.startswith('text/') or mime_type in ['application/json']:
        # Text files - decode directly
        file.seek(0)
        try:
            file_content = file.read().decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError(f"Failed to decode text file {filename}")
    elif mime_type in ['application/pdf', 'application/msword', 
                     'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        # PDF/DOC/DOCX - use extract_text_from_file
        try:
            from chat_utils import extract_text_from_file
            file_content = extract_text_from_file(file, mime_type)
        except Exception as e:
            raise ValueError(f"Failed to extract text from {filename}: {e}")
    elif mime_type == 'application/octet-stream':
        # Try to detect text files with wrong MIME type
        try:
            file.seek(0)
            sample = file.read(1024).decode('utf-8')
            file.seek(0)
            if ext in ['md', 'txt', 'json', 'py', 'js', 'css', 'html', 'csv']:
                file_content = file.read().decode('utf-8')
            else:
                raise ValueError(f"Unsupported binary file type: {filename}")
        except UnicodeDecodeError:
            raise ValueError(f"Unable to process file as text: {filename}")
    else:
        raise ValueError(f"Unsupported file type ({mime_type}): {filename}")

    # Use context monitor for intelligent file content compression
    truncated_content = context_monitor.compress_file_content(
        file_content,
        MAX_FILE_CONTENT_LENGTH
    )

    # Use tiktoken for consistent token counting
    token_count = count_file_tokens(truncated_content)
    context_monitor.track_token_usage(token_count)

    # Cache the processed content
    cache_key = hash((filename, len(file_content)))
    context_manager.context_cache[cache_key] = [{"content": truncated_content}]

    # Check if content was truncated
    if len(truncated_content) < len(file_content):
        logger.info(f"File {filename} was truncated from {len(file_content)} to {len(truncated_content)} characters")
            
    return filename, truncated_content, token_count

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

    if not words:
        return "New Chat"

    word_counts = {}
    for word in words:
        word_counts[word] = word_counts.get(word, 0) + 1

    top_words = sorted(word_counts.keys(), key=lambda x: word_counts.get(x, 0), reverse=True)[:2]
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


def format_file_contents_for_o1(files_data: List[Dict[str, str]], message: str = "") -> str:
    """
    Format file contents in a way that's optimized for o1 series models.
    
    Args:
        files_data: List of dictionaries containing file info and content
        message: Optional user message to include
    
    Returns:
        Formatted string combining message and file contents
    """
    formatted_content = []
    
    # Add user message if present
    if message.strip():
        formatted_content.append(f"User Message: {message.strip()}\n")
    
    # Add file contents with clear section markers
    if files_data:
        formatted_content.append("\n=== Uploaded Files Content ===\n")
        
        for idx, file_data in enumerate(files_data, 1):
            filename = file_data.get('filename', f'File {idx}')
            content = file_data.get('content', '').strip()
            mime_type = file_data.get('mime_type', 'text/plain')
            
            # Add file metadata header
            formatted_content.append(f"\n--- File {idx}: {filename} ({mime_type}) ---\n")
            
            # Format content based on type
            if mime_type.startswith('text/'):
                # For text files, add line numbers and clear section markers
                lines = content.split('\n')
                formatted_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
                formatted_content.append('\n'.join(formatted_lines))
            else:
                # For other types, just add the content with a type indicator
                formatted_content.append(f"[Content Type: {mime_type}]\n{content}")
                
            formatted_content.append("\n" + "-" * 50 + "\n")
    
    # Add a clear end marker
    formatted_content.append("\n=== End of Files ===\n")
    
    return "\n".join(formatted_content)

def process_uploaded_files(files_list):
    """
    Re-introduced so chat_routes.py can import successfully.
    This function calls process_file() to handle each file.
    Returns a tuple of (included_files, excluded_files, total_tokens, file_contents).
    """
    included_files = []
    excluded_files = []
    total_tokens = 0
    file_contents = []
    for f in files_list:
        try:
            filename, truncated_content, token_count = process_file(f)
            included_files.append(f)
            file_contents.append({
                "filename": filename,
                "content": truncated_content
            })
            total_tokens += token_count
        except ValueError as e:
            excluded_files.append({f.filename: str(e)})
    return (included_files, excluded_files, total_tokens, file_contents)

def validate_chat_access(chat_id: str, user_id: str) -> bool:
    """
    Validate if a user has access to a specific chat.
    
    Args:
        chat_id: ID of the chat to validate
        user_id: ID of the user requesting access
        
    Returns:
        bool: True if user has access, False otherwise
    """
    try:
        from models.chat import Chat
        chat = Chat.query.get(chat_id)
        if not chat:
            return False
        return chat.user_id == user_id
    except Exception as e:
        logger.error(f"Error validating chat access: {str(e)}")
        return False
