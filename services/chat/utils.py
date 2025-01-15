import uuid
from typing import List, Dict
from utils.token import count_tokens


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
    tokens = count_tokens(context)
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens]
        context = count_tokens.decode(truncated_tokens)
        context += "\n\n[Note: Context truncated due to token limit.]"

    return context


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

    # Count word frequencies and get top 2 most common
    word_counts = {}
    for word in words:
        word_counts[word] = word_counts.get(word, 0) + 1
    top_words = sorted(word_counts.keys(), key=lambda x: word_counts.get(x, 0), reverse=True)[:2]

    # Create title from top words or fallback to default
    if top_words:
        return " ".join([word.capitalize() for word in top_words])
    return "New Chat"