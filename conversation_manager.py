import logging
import os
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from database import db_session
import tiktoken

# Configure logging
logger = logging.getLogger(__name__)

# Configuration Management via Environment Variables
TOKENS_PER_MESSAGE: int = int(os.getenv("TOKENS_PER_MESSAGE", "3"))
TOKENS_PER_NAME: int = int(os.getenv("TOKENS_PER_NAME", "1"))
TOKENS_PER_ASSISTANT_REPLY: int = int(os.getenv("TOKENS_PER_ASSISTANT_REPLY", "3"))
MAX_MESSAGES: int = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16384"))
MAX_MESSAGE_TOKENS: int = int(os.getenv("MAX_MESSAGE_TOKENS", "8192"))
DEFAULT_MODEL_NAME: str = os.getenv("DEFAULT_MODEL_NAME", "gpt-4")

class ConversationManager:
    """
    Manages conversations by storing and retrieving messages from the database.

    Uses token_utils.count_tokens for token counting and message truncation.
    All token calculations are based on the model specified in MODEL_NAME.

    Attributes:
        tokens_per_message (int): Number of tokens used for message metadata.
        tokens_per_name (int): Extra token for messages with names.
        tokens_per_assistant_reply (int): Tokens for assistant's reply metadata.
        max_messages (int): Maximum number of messages to keep.
        max_tokens (int): Maximum total tokens allowed.
        max_message_tokens (int): Maximum tokens per message.
        default_model_name (str): Default model to use for token counting.
    """

    def __init__(
        self,
        tokens_per_message: int = TOKENS_PER_MESSAGE,
        tokens_per_name: int = TOKENS_PER_NAME,
        tokens_per_assistant_reply: int = TOKENS_PER_ASSISTANT_REPLY,
        max_messages: int = MAX_MESSAGES,
        max_tokens: int = MAX_TOKENS,
        max_message_tokens: int = MAX_MESSAGE_TOKENS,
        default_model_name: str = DEFAULT_MODEL_NAME,
    ):
        self.tokens_per_message = tokens_per_message
        self.tokens_per_name = tokens_per_name
        self.tokens_per_assistant_reply = tokens_per_assistant_reply
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.max_message_tokens = max_message_tokens
        self.default_model_name = default_model_name
        self.encoding = self.get_encoding(default_model_name)

    def get_encoding(self, model_name: str):
        """
        Get the appropriate encoding for the given model.

        Args:
            model_name (str): The name of the model.

        Returns:
            The encoding for the model.
        """
        try:
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.warning(
                f"Model '{model_name}' not found. Falling back to 'cl100k_base' encoding."
            )
            return tiktoken.get_encoding("cl100k_base")

    def num_tokens_from_messages(self, messages: List[Dict[str, str]], model_name: Optional[str] = None) -> int:
        """
        Returns the number of tokens used by a list of messages as per OpenAI's guidelines.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' and 'content' keys.
            model_name (Optional[str]): The model to use for token counting. Defaults to self.default_model_name.

        Returns:
            int: Total number of tokens used by the messages.
        """
        model_name = model_name or self.default_model_name
        encoding = self.get_encoding(model_name)
        num_tokens = 0
        for message in messages:
            num_tokens += self.tokens_per_message
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":
                    num_tokens += self.tokens_per_name

        num_tokens += self.tokens_per_assistant_reply
        return num_tokens

    def get_context(
        self, chat_id: str, model_name: Optional[str] = None, include_system: bool = False
    ) -> List[Dict[str, str]]:
        """
        Retrieve the conversation context for a specific chat ID.

        Args:
            chat_id (str): The unique identifier for the chat session.
            model_name (Optional[str]): The model to use for token counting. Defaults to self.default_model_name.
            include_system (bool): Whether to include system messages. Defaults to False.

        Returns:
            List[Dict[str, str]]: A list of message dictionaries with 'role' and 'content'.
        """
        model_name = model_name or self.default_model_name
        encoding = self.get_encoding(model_name)
        try:
            with db_session() as session:
                query = text(
                    """
                    SELECT id, role, content
                    FROM messages
                    WHERE chat_id = :chat_id
                    ORDER BY timestamp ASC
                    """
                )
                result = session.execute(query, {"chat_id": chat_id}).mappings().all()

                messages = []
                for row in result:
                    content = row["content"]
                    if include_system or row["role"] != "system":
                        messages.append(
                            {
                                "id": row["id"],
                                "role": row["role"],
                                "content": content,
                            }
                        )

                return messages
        except SQLAlchemyError as e:
            logger.error(f"Database error while retrieving context for chat_id {chat_id}: {e}")
            raise

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        model_name: Optional[str] = None,
        model_max_tokens: Optional[int] = None,
        requires_o1_handling: bool = False,
    ) -> None:
        """
        Add a message to the conversation context.
        Truncate user messages if they exceed max_message_tokens.
        Assistant messages are stored without truncation.

        Args:
            chat_id (str): The unique identifier for the chat session.
            role (str): The role of the message sender ("user", "assistant", or "system").
            content (str): The message content to add.
            model_name (Optional[str]): The model to use for token counting. Defaults to self.default_model_name.
            model_max_tokens (Optional[int]): The maximum number of tokens allowed for the model.
            requires_o1_handling (bool): Whether the model requires o1 handling.

        Raises:
            Exception: If there's an error adding the message to the database.
        """
        model_name = model_name or self.default_model_name
        encoding = self.get_encoding(model_name)

        if model_max_tokens is None:
            if requires_o1_handling:
                model_max_tokens = self.max_message_tokens
            else:
                model_max_tokens = self.max_tokens

        if role == "user":
            tokens = encoding.encode(content)
            content = self.truncate_message(
                content, max_tokens=self.max_message_tokens, tokens=tokens
            )

        try:
            with db_session() as session:
                try:
                    # Insert new message
                    insert_query = text(
                        """
                        INSERT INTO messages (chat_id, role, content)
                        VALUES (:chat_id, :role, :content)
                        """
                    )
                    session.execute(
                        insert_query,
                        {"chat_id": chat_id, "role": role, "content": content},
                    )

                    # Retrieve all messages including the new one
                    messages_query = text(
                        """
                        SELECT id, role, content
                        FROM messages
                        WHERE chat_id = :chat_id
                        ORDER BY timestamp ASC
                        """
                    )
                    result = session.execute(
                        messages_query, {"chat_id": chat_id}
                    ).mappings().all()

                    # Convert to message dicts
                    message_dicts = [
                        {"id": msg["id"], "role": msg["role"], "content": msg["content"]}
                        for msg in result
                    ]

                    # Maintain a running total of tokens
                    total_tokens = sum(
                        self.num_tokens_from_messages([msg], model_name=model_name)
                        for msg in message_dicts
                    )

                    # Remove oldest messages to stay within token limit
                    while total_tokens > model_max_tokens and len(message_dicts) > 1:
                        msg_to_remove = message_dicts.pop(0)
                        msg_tokens = self.num_tokens_from_messages(
                            [msg_to_remove], model_name=model_name
                        )
                        delete_query = text("DELETE FROM messages WHERE id = :id")
                        session.execute(delete_query, {"id": msg_to_remove["id"]})
                        total_tokens -= msg_tokens

                    session.commit()
                    logger.debug(
                        f"Added message to chat {chat_id}: {role}: {content[:50]}..."
                    )
                except SQLAlchemyError as e:
                    session.rollback()
                    logger.error(f"Error adding message to chat {chat_id}: {e}")
                    raise
        except Exception as e:
            logger.error(f"Unexpected error while adding message to chat {chat_id}: {e}")
            raise

    def clear_context(self, chat_id: str) -> None:
        """Clear the conversation context for a specific chat ID."""
        try:
            with db_session() as session:
                try:
                    session.execute(
                        text("DELETE FROM messages WHERE chat_id = :chat_id"),
                        {"chat_id": chat_id},
                    )
                    session.commit()
                    logger.debug(f"Cleared context for chat {chat_id}")
                except SQLAlchemyError as e:
                    session.rollback()
                    logger.error(f"Error clearing context for chat {chat_id}: {e}")
                    raise
        except Exception as e:
            logger.error(f"Unexpected error while clearing context for chat {chat_id}: {e}")
            raise

    def truncate_message(
        self, message: str, max_tokens: int, model_name: Optional[str] = None, tokens: Optional[List[int]] = None
    ) -> str:
        """
        Truncate a message to fit within the maximum token limit.

        Args:
            message (str): The message to truncate.
            max_tokens (int): Maximum number of tokens allowed.
            model_name (Optional[str]): The model to use for token counting. Defaults to self.default_model_name.
            tokens (Optional[List[int]]): Optional pre-encoded tokens to avoid re-encoding.

        Returns:
            str: The original message or a truncated version if it exceeds the token limit.
        """
        model_name = model_name or self.default_model_name
        encoding = self.get_encoding(model_name)

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
            chat_id (str): The unique identifier for the chat session.

        Returns:
            Dict[str, int]: Dictionary containing:
            - total_messages: Number of messages in the chat
            - total_tokens: Total number of tokens used by all messages
        """
        try:
            with db_session() as session:
                messages = self.get_context(chat_id, include_system=True)
                total_tokens = self.num_tokens_from_messages(messages)
                return {
                    "total_messages": len(messages),
                    "total_tokens": total_tokens,
                }
        except SQLAlchemyError as e:
            logger.error(f"Database error while retrieving usage stats for chat_id {chat_id}: {e}")
            raise

# Export an instance of ConversationManager
conversation_manager = ConversationManager()