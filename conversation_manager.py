# conversation_manager.py

import logging
from typing import Dict, List
from database import get_db
import os
from chat_utils import count_tokens

logger = logging.getLogger(__name__)

# Retrieve max_messages and max_tokens from environment variables, with default values
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "3500"))


class ConversationManager:
    """Manages conversations by storing and retrieving messages from the database."""

    def __init__(self):
        pass

    def get_context(self, chat_id: str) -> List[Dict[str, str]]:
        """Retrieve the conversation context for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.

        Returns:
            List[Dict[str, str]]: A list of message dictionaries containing 'role' and 'content'.
        """
        db = get_db()
        messages = db.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp",
            (chat_id,),
        ).fetchall()
        # Include all messages, including 'system' messages
        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    def add_message(self, chat_id: str, role: str, content: str) -> None:
        """Add a message to the conversation context.

        Args:
            chat_id (str): The unique identifier for the chat session.
            role (str): The role of the sender ('user', 'assistant', 'system').
            content (str): The message content.
        """
        db = get_db()
        db.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        db.commit()
        self.trim_context(chat_id)
        logger.debug(f"Added message to chat {chat_id}: {role}: {content[:50]}...")

    def clear_context(self, chat_id: str) -> None:
        """Clear the conversation context for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.
        """
        db = get_db()
        db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        db.commit()
        logger.debug(f"Cleared context for chat {chat_id}")

    def trim_context(
        self,
        chat_id: str,
        max_messages: int = MAX_MESSAGES,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        """Trim the conversation context based on the number of messages and total tokens.

        Removes the oldest messages if either the number of messages exceeds max_messages
        or the total number of tokens exceeds max_tokens.

        Args:
            chat_id (str): The unique identifier for the chat session.
            max_messages (int): The maximum number of messages to retain.
            max_tokens (int): The maximum number of tokens to retain.
        """
        db = get_db()
        messages = self.get_context(chat_id)

        # Trim based on number of messages
        if len(messages) > max_messages:
            excess = len(messages) - max_messages
            db.execute(
                """
                DELETE FROM messages
                WHERE id IN (
                    SELECT id
                    FROM messages
                    WHERE chat_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
                """,
                (chat_id, excess),
            )
            db.commit()
            logger.debug(
                f"Trimmed context for chat {chat_id} "
                f"to the most recent {max_messages} messages"
            )

        # Trim based on token count
        total_tokens = sum(count_tokens(msg["content"]) for msg in messages)
        while total_tokens > max_tokens:
            oldest_message = db.execute(
                "SELECT id, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC LIMIT 1",
                (chat_id,),
            ).fetchone()

            if oldest_message:
                db.execute("DELETE FROM messages WHERE id = ?", (oldest_message["id"],))
                db.commit()
                total_tokens -= count_tokens(oldest_message["content"])
                logger.debug(
                    f"Trimmed context for chat {chat_id} due to exceeding token limit"
                )
            else:
                break  # No more messages to trim

    def set_model(self, chat_id: str, model_id: int) -> None:
        """Set the model for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.
            model_id (int): The ID of the model to be set.
        """
        db = get_db()
        db.execute(
            "UPDATE chats SET model_id = ? WHERE id = ?",
            (model_id, chat_id),
        )
        db.commit()
        logger.info(f"Model set for chat {chat_id}: Model ID {model_id}")

    def get_model(self, chat_id: str) -> int:
        """Retrieve the model ID for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.

        Returns:
            int: The ID of the model associated with the chat.
        """
        db = get_db()
        chat = db.execute(
            "SELECT model_id FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        return chat["model_id"] if chat and chat["model_id"] is not None else None

    def migrate_chats(self, old_model_id: int, new_model_id: int) -> None:
        """Migrate chats from one model to another.

        Args:
            old_model_id (int): The ID of the old model.
            new_model_id (int): The ID of the new model.
        """
        db = get_db()
        db.execute(
            "UPDATE chats SET model_id = ? WHERE model_id = ?",
            (new_model_id, old_model_id),
        )
        db.commit()
        logger.info(f"Migrated chats from model {old_model_id} to model {new_model_id}")

    def get_usage_stats(self, chat_id: str) -> Dict[str, int]:
        """Retrieve usage statistics for a specific chat.

        Args:
            chat_id (str): The unique identifier for the chat session.

        Returns:
            Dict[str, int]: A dictionary containing usage statistics (e.g., token count).
        """
        messages = self.get_context(chat_id)
        total_tokens = sum(count_tokens(msg["content"]) for msg in messages)
        return {
            "total_messages": len(messages),
            "total_tokens": total_tokens,
        }
