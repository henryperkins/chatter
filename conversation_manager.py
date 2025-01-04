import logging
import os
from typing import Dict, List
import tiktoken
from database import get_db

logger = logging.getLogger(__name__)

# Configurable Environment Variables (with defaults)
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "3500"))
MAX_MESSAGE_TOKENS = int(os.getenv("MAX_MESSAGE_TOKENS", "500"))
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")  # Model for tiktoken


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string.

    Args:
        text: The text to count tokens for

    Returns:
        Number of tokens in the text
    """
    try:
        encoding = tiktoken.encoding_for_model(MODEL_NAME)
        return len(encoding.encode(text))
    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        # Return a conservative estimate if token counting fails
        return len(text) // 4  # Rough approximation


class ConversationManager:
    """Manages conversations by storing and retrieving messages from the database."""

    def __init__(self):
        self.encoding = tiktoken.encoding_for_model(MODEL_NAME)

    def get_context(
        self, chat_id: str, include_system: bool = False
    ) -> List[Dict[str, str]]:
        """Retrieve the conversation context for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.
            include_system (bool): Whether to include system messages. Defaults to False.

        Returns:
            List[Dict[str, str]]: A list of message dictionaries containing 'role' and 'content'.
        """
        db = get_db()
        messages = db.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp",
            (chat_id,),
        ).fetchall()

        if include_system:
            return [
                {"role": msg["role"], "content": msg["content"]} for msg in messages
            ]
        else:
            return [
                {"role": msg["role"], "content": msg["content"]}
                for msg in messages
                if msg["role"] != "system"
            ]

    def add_message(self, chat_id: str, role: str, content: str) -> None:
        """Add a message to the conversation context.

        Args:
            chat_id (str): The unique identifier for the chat session.
            role (str): The role of the sender ('user', 'assistant', 'system').
            content (str): The message content.
        """
        db = get_db()

        # Truncate the message if it's too long
        content = self.truncate_message(content, max_tokens=MAX_MESSAGE_TOKENS)

        try:
            db.execute(
                "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content),
            )
            db.commit()
            self.trim_context(chat_id)
            logger.debug(f"Added message to chat {chat_id}: {role}: {content[:50]}...")
        except Exception as e:
            logger.error(f"Error adding message to chat {chat_id}: {e}")
            db.rollback()

    def clear_context(self, chat_id: str) -> None:
        """Clear the conversation context for a specific chat ID."""
        db = get_db()
        try:
            db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            db.commit()
            logger.debug(f"Cleared context for chat {chat_id}")
        except Exception as e:
            logger.error(f"Error clearing context for chat {chat_id}: {e}")
            db.rollback()

    def trim_context(self, chat_id: str) -> None:
        """Trim the conversation context to stay within limits."""
        db = get_db()
        messages = self.get_context(chat_id)

        # Trim based on number of messages
        if len(messages) > MAX_MESSAGES:
            excess_messages = len(messages) - MAX_MESSAGES
            try:
                db.execute(
                    """
                    DELETE FROM messages WHERE id IN (
                        SELECT id FROM messages
                        WHERE chat_id = ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                    """,
                    (chat_id, excess_messages),
                )
                db.commit()
            except Exception as e:
                logger.error(f"Error trimming messages for chat {chat_id}: {e}")
                db.rollback()
                return

        # Trim based on token count
        total_tokens = sum(count_tokens(msg["content"]) for msg in messages)
        while total_tokens > MAX_TOKENS and messages:
            try:
                # Delete oldest message
                db.execute(
                    """
                    DELETE FROM messages WHERE id = (
                        SELECT id FROM messages
                        WHERE chat_id = ?
                        ORDER BY timestamp ASC
                        LIMIT 1
                    )
                    """,
                    (chat_id,),
                )
                db.commit()

                # Recalculate total tokens
                messages = self.get_context(chat_id)
                total_tokens = sum(count_tokens(msg["content"]) for msg in messages)
            except Exception as e:
                logger.error(f"Error trimming tokens for chat {chat_id}: {e}")
                db.rollback()
                break

    def truncate_message(self, message: str, max_tokens: int) -> str:
        """Truncate a message to fit within the maximum token limit."""
        tokens = self.encoding.encode(message)
        if len(tokens) > max_tokens:
            truncated_tokens = tokens[:max_tokens]
            truncated_message = self.encoding.decode(truncated_tokens)
            truncated_message += "\n\n[Note: The input was truncated.]"
            logger.warning(
                f"Message truncated to {max_tokens} tokens. Original tokens: {len(tokens)}."
            )
            return truncated_message
        return message

    def get_usage_stats(self, chat_id: str) -> Dict[str, int]:
        """Get usage statistics for a chat session."""
        messages = self.get_context(chat_id)
        total_tokens = sum(count_tokens(msg["content"]) for msg in messages)
        return {
            "total_messages": len(messages),
            "total_tokens": total_tokens,
        }
