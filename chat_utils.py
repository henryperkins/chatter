import uuid
from typing import List, Dict
from werkzeug.utils import secure_filename as werkzeug_secure_filename


def count_tokens(text: str, model_name: str) -> int:
    """
    Count the number of tokens in a given text for a specific model.
    This is a placeholder function. Replace with actual token counting logic.
    """
    return len(text.split())


def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it is safe for storage.
    """
    return werkzeug_secure_filename(filename)


def generate_new_chat_id() -> str:
    """Generate a new unique chat ID."""
    return str(uuid.uuid4())


def extract_context_from_conversation(messages: List[Dict[str, str]], latest_response: str) -> str:
    """
    Extract key context from the conversation.

    Args:
        messages: List of message dictionaries, each containing 'role' and 'content' keys.
        latest_response: The latest response from the model.

    Returns:
        A string containing the extracted context, limited to 4000 characters.
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

    # Join all parts with newlines and limit to 4000 characters
    return "\n".join(context_parts)[:4000]
