import tiktoken
import os
from typing import Any, List, Dict, Literal, TypedDict, Optional
from functools import lru_cache
from logging_config import get_logger

logger = get_logger("token_usage")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")
logger.info("Initializing token utils with model: %s", MODEL_NAME)

# Special tokens for chat models
SPECIAL_TOKENS = {
    "<|im_start|>": 100264,
    "<|im_end|>": 100265,
    "<|im_sep|>": 100266
}

def get_encoding(model_name: str = MODEL_NAME):
    """Initialize and return the tiktoken encoding for the specified model."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        # Add special tokens for chat models
        if model_name.startswith("gpt-"):
            encoding._special_tokens = SPECIAL_TOKENS
        return encoding
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")

@lru_cache(maxsize=1000)
def cached_count_tokens(text: str, model_name: str = MODEL_NAME) -> int:
    """Count tokens with caching for better performance."""
    encoding = get_encoding(model_name)
    return len(encoding.encode(text))

def count_tokens(text: str, model_name: str = MODEL_NAME) -> int:
    """
    Count tokens in the provided text.
    This is a backward-compatible wrapper for cached_count_tokens.
    """
    return cached_count_tokens(text, model_name)

class MessageDict(TypedDict):
    """Type-safe dictionary for chat messages."""
    role: Literal["system", "user", "assistant"]
    content: str
    max_tokens: Optional[int]
    token_count: Optional[int]
    is_first: Optional[bool]

def validate_message(message: dict) -> bool:
    """Validate message structure and content."""
    try:
        msg = MessageDict(**message)
        return True
    except (TypeError, ValueError):
        return False

def count_message_tokens(message: dict) -> int:
    """Count tokens for a single message with role metadata."""
    logger.debug("Counting tokens for message: %s", message)

    if not validate_message(message):
        message = {"role": "user", "content": ""}
        logger.warning("Invalid message format, returning 0 tokens")
        return 0

    tokens = 0

    # Add API-specific formatting tokens
    if MODEL_NAME.startswith("gpt-"):
        tokens += 2  # Start token
        tokens += 1  # End token
        tokens += 1  # Separator token
        logger.debug("Added 3 tokens for GPT formatting")

    # Add role-specific overhead
    if message["role"] == "system":
        tokens += 4
        logger.debug("Added 4 tokens for system role")
    elif message["role"] == "user":
        tokens += 3
        logger.debug("Added 3 tokens for user role")
    elif message["role"] == "assistant":
        tokens += 3
        logger.debug("Added 3 tokens for assistant role")

    # Add message content tokens
    content_tokens = cached_count_tokens(message["content"])
    logger.debug("Content tokens: %d for content length %d",
                 content_tokens, len(message["content"]))
    tokens += content_tokens

    # Add multi-message overhead if not first message
    if message.get("is_first", False):
        tokens += 2
        logger.debug("Added 2 tokens for multi-message overhead")
    tokens += 1  # End token

    logger.debug("Total tokens for message: %d", tokens)
    return tokens

def count_conversation_tokens(messages: List[dict]) -> int:
    """Count total tokens for a conversation."""
    total = 0

    # System message overhead
    if messages and messages[0]["role"] == "system":
        total += 4

    # Count each message
    for i, message in enumerate(messages):
        total += count_message_tokens(message)

        # Add reply overhead
        if i > 0:
            total += 3

    # Add safety buffer
    total += 20

    return total

def estimate_tokens(text: str) -> int:
    """Fallback token estimation when encoding fails."""
    if not text:
        return 0

    char_count = len(text)
    if char_count < 100:
        return char_count // 2
    elif char_count < 1000:
        return char_count // 3
    else:
        return char_count // 4

def truncate_content(content: str, max_tokens: int, note: str = "[Content truncated due to token limit]") -> str:
    """Truncate content to fit within the specified token limit."""
    try:
        encoding = get_encoding()
        tokens = encoding.encode(content)
        if len(tokens) > max_tokens:
            # Leave room for truncation note
            truncated_tokens = tokens[:max_tokens - cached_count_tokens(note)]
            truncated_content = encoding.decode(truncated_tokens)
            return f"{truncated_content}\n\n{note}"
        return content
    except Exception:
        # Fallback to character-based truncation
        estimated_tokens = estimate_tokens(content)
        if estimated_tokens > max_tokens:
            max_chars = max_tokens * 4  # Conservative estimate
            return content[:max_chars] + f"\n\n{note}"
        return content
