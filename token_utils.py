import tiktoken
import logging

logger = logging.getLogger(__name__)

def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """
    Count the number of tokens in a text using the tokenizer for the specified model.

    Args:
        text: The text to tokenize and count.
        model_name: The name of the model to use for tokenization (default: gpt-3.5-turbo).

    Returns:
        The number of tokens in the text.

    Raises:
        ValueError: If the model encoding is not found.
    """
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        logger.error(f"Encoding not found for model '{model_name}'")
        raise ValueError(f"Token encoding not found for model '{model_name}'")
    return len(encoding.encode(text))
