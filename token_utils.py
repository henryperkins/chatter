import tiktoken
import os
from typing import Any

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")

def get_encoding():
    """Initialize and return the tiktoken encoding for the specified model."""
    try:
        encoding = tiktoken.encoding_for_model(MODEL_NAME)
        # Add special tokens for chat models
        if MODEL_NAME.startswith("gpt-4") or MODEL_NAME.startswith("gpt-3.5"):
            encoding._special_tokens = {
                "<|im_start|>": 100264,
                "<|im_end|>": 100265,
                "<|im_sep|>": 100266
            }
        return encoding
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")

def count_message_tokens(message: dict, encoding: Any) -> int:
    """Count tokens for a single message with role metadata."""
    tokens = 0
    # Add special tokens for chat models
    if MODEL_NAME.startswith("gpt-4") or MODEL_NAME.startswith("gpt-3.5"):
        tokens += 3  # <|im_start|> + role + \n
        if message.get("name"):
            tokens += 1  # name token
            
    # Count content tokens
    tokens += len(encoding.encode(message.get("content", "")))
    
    # Add special tokens for chat models
    if MODEL_NAME.startswith("gpt-4") or MODEL_NAME.startswith("gpt-3.5"):
        tokens += 1  # <|im_end|>
    
    return tokens

def truncate_content(content: str, max_tokens: int, note: str = "[Content truncated due to token limit]") -> str:
    """Truncate content to fit within the specified token limit."""
    encoding = get_encoding()
    tokens = encoding.encode(content)
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens - 50]  # Leave room for truncation note
        truncated_content = encoding.decode(truncated_tokens)
        return f"{truncated_content}\n\n{note}"
    return content
