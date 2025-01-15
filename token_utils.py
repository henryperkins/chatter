import tiktoken
import os
from typing import Any, List, Dict
from functools import lru_cache

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")

# Special tokens for chat models
SPECIAL_TOKENS = {
    "<|im_start|>": 100264,
    "<|im_end|>": 100265,
    "<|im_sep|>": 100266
}

def get_encoding():
    """Initialize and return the tiktoken encoding for the specified model."""
    try:
        encoding = tiktoken.encoding_for_model(MODEL_NAME)
        # Add special tokens for chat models
        if MODEL_NAME.startswith("gpt-"):
            encoding._special_tokens = SPECIAL_TOKENS
        return encoding
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")

@lru_cache(maxsize=1000)
def cached_count_tokens(text: str) -> int:
    """Count tokens with caching for better performance."""
    encoding = get_encoding()
    return len(encoding.encode(text))

def validate_message(message: dict) -> bool:
    """Validate message structure and content."""
    required_keys = {"role", "content"}
    if not all(key in message for key in required_keys):
        return False
    if not isinstance(message["content"], str):
        return False
    return True

def count_message_tokens(message: dict) -> int:
    """Count tokens for a single message with role metadata."""
    if not validate_message(message):
        return 0
        
    tokens = 0
    
    # Add API-specific formatting tokens
    if MODEL_NAME.startswith("gpt-"):
        tokens += 2  # Start token
        tokens += 1  # End token
        
    # Add role-specific overhead
    if message["role"] == "system":
        tokens += 4
    elif message["role"] == "user":
        tokens += 3
    elif message["role"] == "assistant":
        tokens += 3
        
    # Add message content tokens
    tokens += cached_count_tokens(message["content"])
    
    # Add multi-message overhead if not first message
    if message.get("is_first", False):
        tokens += 2
        
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
