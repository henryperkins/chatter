from models import Chat
import uuid
import tiktoken


def generate_new_chat_id():
    return str(uuid.uuid4())


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Counts the number of tokens in a string.

    Args:
        text: The input string.
        model: The model name to use for tokenization.

    Returns:
        The number of tokens in the string.
    """
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = len(encoding.encode(text))
    return num_tokens


def extract_context_from_conversation(messages, latest_response):
    """
    Extract key context from the conversation.

    Args:
        messages (list): List of messages in the conversation.
        latest_response (str): The latest response from the model.

    Returns:
        str: Extracted context from the conversation.
    """
    context_parts = []
    for msg in messages[-10:]:  # Consider last 10 messages for context
        if msg["role"] in ["assistant", "user"]:
            context_parts.append(f"{msg['role']}: {msg['content']}")

    context_parts.append(f"assistant: {latest_response}")

    context = "\n".join(context_parts)
    return context[:4000]  # Limit context to 4000 characters
