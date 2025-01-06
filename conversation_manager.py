import logging
import os
from typing import Dict, List

import tiktoken
from database import db_connection  # Use the centralized context manager
from chat_utils import count_tokens  # Import the count_tokens function

logger = logging.getLogger(__name__)

# Configurable Environment Variables (with defaults)
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "3500"))
MAX_MESSAGE_TOKENS = int(os.getenv("MAX_MESSAGE_TOKENS", "500"))
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")  # Model for tiktoken

class ConversationManager:
    """Manages conversations by storing and retrieving messages from the database."""

    def __init__(self):
        try:
            self.encoding = tiktoken.encoding_for_model(MODEL_NAME)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def num_tokens_from_messages(self, messages: List[Dict[str, str]]) -> int:
        """
        Returns the number of tokens used by a list of messages as per OpenAI's guidelines.
        """
        tokens_per_message = 3  # Includes role and message separators
        tokens_per_assistant_reply = 3  # Accounts for assistant's reply tokens
        num_tokens = 0

        for message in messages:
            num_tokens += tokens_per_message
            num_tokens += len(self.encoding.encode(message["content"]))
            if message.get("name"):  # If there's a name field, add an extra token
                num_tokens += 1

        num_tokens += tokens_per_assistant_reply
        return num_tokens

    def get_context(self, chat_id: str, include_system: bool = False) -> List[Dict[str, str]]:
        """
        Retrieve the conversation context for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.
            include_system (bool): Whether to include system messages. Defaults to False.

        Returns:
            A list of message dictionaries with 'role' and 'content'.
        """
        with db_connection() as db:
            # Explicitly order by timestamp ascending
            messages = db.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE chat_id = ?
                ORDER BY timestamp ASC
                """,
                (chat_id,),
            ).fetchall()

            if include_system:
                return [
                    {"id": msg["id"], "role": msg["role"], "content": msg["content"]}
                    for msg in messages
                ]
            else:
                return [
                    {"id": msg["id"], "role": msg["role"], "content": msg["content"]}
                    for msg in messages
                    if msg["role"] != "system"
                ]

    def add_message(self, chat_id: str, role: str, content: str) -> None:
        """
        Add a message to the conversation context, ensuring it doesn't exceed
        MAX_MESSAGE_TOKENS (accounting for overhead).
        """
        # Truncate the message if it's too long
        content = self.truncate_message(content, max_tokens=MAX_MESSAGE_TOKENS)

        try:
            with db_connection() as db:
                # Insert new message
                db.execute(
                    "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                    (chat_id, role, content),
                )

                # Get all messages including the new one
                messages = db.execute(
                    """
                    SELECT id, role, content
                    FROM messages
                    WHERE chat_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (chat_id,),
                ).fetchall()

                # Convert to message dicts
                message_dicts = [
                    {"id": msg["id"], "role": msg["role"], "content": msg["content"]}
                    for msg in messages
                ]

                # Trim based on total token count
                total_tokens = self.num_tokens_from_messages(message_dicts)
                while total_tokens > MAX_TOKENS and len(message_dicts) > 1:
                    # Remove oldest message to stay within token limit
                    msg_to_remove = message_dicts.pop(0)
                    db.execute(
                        "DELETE FROM messages WHERE id = ?",
                        (msg_to_remove["id"],)
                    )
                    total_tokens = self.num_tokens_from_messages(message_dicts)

                logger.debug(f"Added message to chat {chat_id}: {role}: {content[:50]}...")
        except Exception as e:
            logger.error(f"Error adding message to chat {chat_id}: {e}")
            raise

    def clear_context(self, chat_id: str) -> None:
        """Clear the conversation context for a specific chat ID."""
        with db_connection() as db:
            db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            logger.debug(f"Cleared context for chat {chat_id}")

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
        messages = self.get_context(chat_id, include_system=True)
        total_tokens = self.num_tokens_from_messages(messages)
        return {
            "total_messages": len(messages),
            "total_tokens": total_tokens,
        }
