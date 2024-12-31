# conversation_manager.py

import logging
from typing import Dict, List
from database import get_db
import os

logger = logging.getLogger(__name__)

# Retrieve max_messages from environment variable, default to 20
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "20"))


class ConversationManager:
    """Manages conversations by storing and retrieving messages from the database."""

    def __init__(self):
        # Initialization is not required since we interact directly with the database
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
        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    def add_message(self, chat_id: str, role: str, content: str) -> None:
        """Add a message to the conversation context.

        Args:
            chat_id (str): The unique identifier for the chat session.
            role (str): The role of the sender ('user' or 'assistant').
            content (str): The message content.
        """
        db = get_db()
        db.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        db.commit()
        logger.debug(f"Added message to chat {chat_id}: " f"{role}: {content[:50]}...")

    def clear_context(self, chat_id: str) -> None:
        """Clear the conversation context for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.
        """
        db = get_db()
        db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        db.commit()
        logger.debug(f"Cleared context for chat {chat_id}")

    def trim_context(self, chat_id: str, max_messages: int = MAX_MESSAGES) -> None:
        """Trim the conversation context to maintain a maximum number of messages.

        Removes the oldest messages to keep the context within the specified limit.

        Args:
            chat_id (str): The unique identifier for the chat session.
            max_messages (int, optional): The maximum number of messages to retain. Defaults to MAX_MESSAGES.
        """
        db = get_db()
        messages = db.execute(
            """
            SELECT id FROM messages
            WHERE chat_id = ?
            ORDER BY timestamp ASC
            LIMIT (SELECT COUNT(*) FROM messages WHERE chat_id = ?) - ?
            """,
            (chat_id, chat_id, max_messages),
        ).fetchall()
        if messages:
            message_ids = [str(msg["id"]) for msg in messages]
            db.execute(
                f"DELETE FROM messages WHERE id IN ({','.join(['?'] * len(message_ids))})",
                message_ids,
            )
            db.commit()
            logger.debug(
                f"Trimmed context for chat {chat_id} "
                f"to the most recent {max_messages} messages"
            )
