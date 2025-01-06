import tiktoken


def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """
    Count the number of tokens in a text using the tokenizer for the specified model.

    Args:
        text: The text to tokenize and count.
        model_name: The name of the model to use for tokenization (default: gpt-3.5-turbo).

    Returns:
        The number of tokens in the text.

    Raises:
        KeyError: If the model is not found, falls back to cl100k_base encoding.
    """
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        # Fallback to a default encoding if model not found
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))
