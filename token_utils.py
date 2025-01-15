import tiktoken
import os
from typing import Any

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")

def get_encoding():
    """Initialize and return the tiktoken encoding for the specified model."""
    try:
        return tiktoken.encoding_for_model(MODEL_NAME)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")

def truncate_content(content: str, max_tokens: int, note: str = "[Content truncated due to token limit]") -> str:
    """Truncate content to fit within the specified token limit."""
    encoding = get_encoding()
    tokens = encoding.encode(content)
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens]
        truncated_content = encoding.decode(truncated_tokens)
        return f"{truncated_content}\n\n{note}"
    return content
