import logging
import os
from typing import Dict, List, Optional

from sqlalchemy import text
from database import get_db
from token_utils import count_tokens
import tiktoken

logger = logging.getLogger(__name__)

# Token-related constants
TOKENS_PER_MESSAGE: int = 3  # Includes role and message separators
TOKENS_PER_NAME: int = 1  # Extra token for messages with names
TOKENS_PER_ASSISTANT_REPLY: int = 3  # Accounts for assistant's reply tokens

# Configurable Environment Variables (with defaults)
MAX_MESSAGES: int = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16384"))  # Adjusted for GPT-4 16K model
MAX_MESSAGE_TOKENS: int = int(
    os.getenv("MAX_MESSAGE_TOKENS", "8192")
)  # GPT-4 input limit
MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4")  # Model for token counting


class ConversationManager:
    """
    Manages conversations by storing and retrieving messages from the database.

    Uses token_utils.count_tokens for token counting and message truncation.
    All token calculations are based on the model specified in MODEL_NAME.

    Class Attributes:
        TOKENS_PER_MESSAGE (int): Number of tokens used for message metadata (3)
        TOKENS_PER_NAME (int): Extra token for messages with names (1)
        TOKENS_PER_ASSISTANT_REPLY (int): Tokens for assistant's reply metadata (3)
        MAX_MESSAGES (int): Maximum number of messages to keep (default: 20)
        MAX_TOKENS (int): Maximum total tokens allowed (default: 16384)
        MAX_MESSAGE_TOKENS (int): Maximum tokens per message (default: 8192)
        MODEL_NAME (str): Model to use for token counting (default: gpt-4)
    """

    def num_tokens_from_messages(self, messages: List[Dict[str, str]]) -> int:
        """
        Returns the number of tokens used by a list of messages as per OpenAI's guidelines.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.

        Returns:
            Total number of tokens used by the messages.
        """
        num_tokens = 0
        for message in messages:
            num_tokens += TOKENS_PER_MESSAGE
            num_tokens += count_tokens(message["content"], MODEL_NAME)
            if message.get("name"):  # If there's a name field, add an extra token
                num_tokens += TOKENS_PER_NAME

        num_tokens += TOKENS_PER_ASSISTANT_REPLY
        return num_tokens

    def get_context(
        self, chat_id: str, include_system: bool = False
    ) -> List[Dict[str, str]]:
        """
        Retrieve the conversation context for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.
            include_system (bool): Whether to include system messages. Defaults to False.

        Returns:
            A list of message dictionaries with 'role' and 'content'.
        """
        db = get_db()
        try:
            messages = (
                db.execute(
                    text(
                        """
                SELECT id, role, content
                FROM messages
                WHERE chat_id = :chat_id
                ORDER BY timestamp ASC
                """
                    ),
                    {"chat_id": chat_id},
                )
                .mappings()
                .all()
            )

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
        finally:
            db.close()

    def add_message(
        self, chat_id: str, role: str, content: str, model_max_tokens: int = MAX_TOKENS
    ) -> None:
        """
        Add a message to the conversation context.
        Truncate user messages if they exceed MAX_MESSAGE_TOKENS.
        Assistant messages are stored without truncation.

        Args:
            chat_id: The unique identifier for the chat session.
            role: The role of the message sender ("user", "assistant", or "system").
            content: The message content to add.
            model_max_tokens: The maximum number of tokens allowed for the model.

        Raises:
            Exception: If there's an error adding the message to the database.
        """
        try:
            encoding = tiktoken.encoding_for_model(MODEL_NAME)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        if role == "user":
            # Truncate user messages if necessary
            tokens = encoding.encode(content)
            content = self.truncate_message(
                content, max_tokens=MAX_MESSAGE_TOKENS, tokens=tokens
            )
        # Assistant messages are not truncated

        db = get_db()
        try:
            # Insert new message
            db.execute(
                text(
                    """
                    INSERT INTO messages (chat_id, role, content)
                    VALUES (:chat_id, :role, :content)
                    """
                ),
                {"chat_id": chat_id, "role": role, "content": content},
            )
            db.commit()

            # Retrieve all messages including the new one
            messages = (
                db.execute(
                    text(
                        """
                    SELECT id, role, content
                    FROM messages
                    WHERE chat_id = :chat_id
                    ORDER BY timestamp ASC
                    """
                    ),
                    {"chat_id": chat_id},
                )
                .mappings()
                .all()
            )

            # Convert to message dicts
            message_dicts = [
                {"id": msg["id"], "role": msg["role"], "content": msg["content"]}
                for msg in messages
            ]

            # Maintain a running total of tokens
            total_tokens = sum(
                self.num_tokens_from_messages([msg]) for msg in message_dicts
            )

            while total_tokens > model_max_tokens and len(message_dicts) > 1:
                # Remove oldest message to stay within token limit
                msg_to_remove = message_dicts.pop(0)
                msg_tokens = self.num_tokens_from_messages([msg_to_remove])
                db.execute(
                    text("DELETE FROM messages WHERE id = :id"),
                    {"id": msg_to_remove["id"]},
                )
                db.commit()
                total_tokens -= msg_tokens

            logger.debug(f"Added message to chat {chat_id}: {role}: {content[:50]}...")
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding message to chat {chat_id}: {e}")
            raise
        finally:
            db.close()

    def clear_context(self, chat_id: str) -> None:
        """Clear the conversation context for a specific chat ID."""
        db = get_db()
        try:
            db.execute(
                text("DELETE FROM messages WHERE chat_id = :chat_id"),
                {"chat_id": chat_id},
            )
            db.commit()
            logger.debug(f"Cleared context for chat {chat_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error clearing context for chat {chat_id}: {e}")
            raise
        finally:
            db.close()

    def truncate_message(
        self, message: str, max_tokens: int, tokens: Optional[List[int]] = None
    ) -> str:
        """
        Truncate a message to fit within the maximum token limit.

        Args:
            message: The message to truncate.
            max_tokens: Maximum number of tokens allowed.
            tokens: Optional pre-encoded tokens to avoid re-encoding.

        Returns:
            The original message or a truncated version if it exceeds the token limit.
        """
        try:
            encoding = tiktoken.encoding_for_model(MODEL_NAME)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        # Use provided tokens if available, otherwise encode the message
        message_tokens = tokens if tokens is not None else encoding.encode(message)
        num_tokens = len(message_tokens)

        if num_tokens > max_tokens:
            truncated_tokens = message_tokens[:max_tokens]
            truncated_message = encoding.decode(truncated_tokens)
            truncated_message += "\n\n[Note: The input was truncated.]"
            logger.warning(
                f"Message truncated to {max_tokens} tokens. Original tokens: {num_tokens}."
            )
            return truncated_message
        return message

    def get_usage_stats(self, chat_id: str) -> Dict[str, int]:
        """
        Get usage statistics for a chat session.

        Args:
            chat_id: The unique identifier for the chat session.

        Returns:
            Dictionary containing:
            - total_messages: Number of messages in the chat
            - total_tokens: Total number of tokens used by all messages
        """
        messages = self.get_context(chat_id, include_system=True)
        total_tokens = self.num_tokens_from_messages(messages)
        return {
            "total_messages": len(messages),
            "total_tokens": total_tokens,
        }


# Export an instance of ConversationManager
conversation_manager = ConversationManager()
