from typing import Tuple
from werkzeug.utils import secure_filename as werkzeug_secure_filename
import os
from utils.config import Config
from utils.token import count_tokens, truncate_content


def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it is safe for storage.

    Args:
        filename (str): The original filename.

    Returns:
        str: A sanitized version of the filename.
    """
    return werkzeug_secure_filename(filename)


def allowed_file(filename: str) -> bool:
    """
    Check if the file has an allowed extension.

    Args:
        filename (str): The filename to check.

    Returns:
        bool: True if the file extension is allowed, False otherwise.
    """
    return os.path.splitext(filename)[1].lower() in Config.ALLOWED_FILE_EXTENSIONS


def process_file(file) -> Tuple[str, str, int]:
    """
    Process an uploaded file by validating, truncating, and reading its content.

    Args:
        file: The uploaded file object.

    Returns:
        Tuple[str, str, int]: A tuple containing the filename, truncated content, and token count.

    Raises:
        ValueError: If the file is invalid or cannot be processed.
    """
    filename = secure_filename(file.filename)
    mime_type = file.mimetype

    # Check MIME type
    if mime_type not in Config.MIME_TYPE_MAP.values():
        raise ValueError(f"File type ({mime_type}) not allowed: {filename}")

    # Check file size
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    if file_length > Config.MAX_FILE_SIZE:
        raise ValueError(f"File too large: {filename} exceeds the {Config.MAX_FILE_SIZE} byte limit.")

    # Process text-based files
    if mime_type.startswith("text/"):
        try:
            file_content = file.read().decode("utf-8")
            truncated_content = truncate_content(
                file_content, 
                Config.MAX_FILE_CONTENT_LENGTH, 
                "[Note: Input truncated due to token limit.]"
            )
            token_count = count_tokens(truncated_content)
            return filename, truncated_content, token_count
        except UnicodeDecodeError as e:
            raise ValueError(f"Failed to decode file {filename}: {e}")
    else:
        raise ValueError(f"Unsupported file type: {filename}")