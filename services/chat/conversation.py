import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from sqlalchemy import text
from services.database import db_session
from services.database.models import Chat
from utils.config import Config
from utils.token import count_tokens

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversations by storing and retrieving messages from the database.

    Uses token_utils.count_tokens for token counting and message truncation.
    All token calculations are based on the model specified in Config.MODEL_NAME.

    Class Attributes:
        MAX_MESSAGES (int): Maximum number of messages to keep.
        MAX_TOKENS (int): Maximum total tokens allowed.
        MAX_MESSAGE_TOKENS (int): Maximum tokens per message.
        MODEL_NAME (str): Model to use for token counting.
    """

    MAX_MESSAGES = Config.MAX_MESSAGES
    MAX_TOKENS = Config.MAX_TOKENS
    MAX_MESSAGE_TOKENS = Config.MAX_MESSAGE_TOKENS
    MODEL_NAME = Config.MODEL_NAME

    def num_tokens_from_messages(self, messages: List[Dict[str, str]]) -> int:
        """
        Returns the number of tokens used by a list of messages.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' and 'content' keys.

        Returns:
            int: Total number of tokens used by the messages.
        """
        num_tokens = 0
        for message in messages:
            # Add role-specific base tokens
            if message["role"] == "system":
                num_tokens += 4  # Base tokens for system messages
            elif message["role"] == "user":
                num_tokens += 4  # Base tokens for user messages
            elif message["role"] == "assistant":
                num_tokens += 4  # Base tokens for assistant messages

            # Count content tokens
            content_tokens = count_tokens(message["content"], self.MODEL_NAME)
            num_tokens += content_tokens

            # Add to message metadata if available
            if isinstance(message.get("metadata"), dict):
                message["metadata"]["token_count"] = content_tokens

        return num_tokens

    def get_context(
        self, chat_id: str, include_system: bool = False
    ) -> List[Dict[str, str]]:
        """
        Retrieve the conversation context with proper formatting.

        Args:
            chat_id (str): The unique identifier for the chat session.
            include_system (bool): Whether to include system messages. Defaults to False.

        Returns:
            List[Dict[str, str]]: A list of message dictionaries with 'role' and 'content'.
        """
        messages = Chat.get_messages(chat_id=chat_id, include_system=include_system)
        context: List[Dict[str, str]] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            metadata = msg.get("metadata", {})

            if isinstance(role, str) and isinstance(content, str):
                message_dict = {"role": role}

                # For assistant messages, use formatted content if available
                if role == "assistant" and metadata and "formatted_content" in metadata:
                    message_dict["content"] = metadata["formatted_content"]
                    message_dict["raw_content"] = metadata["raw_content"]
                else:
                    message_dict["content"] = content

                context.append(message_dict)

        return context

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        model_max_tokens: Optional[int] = None,
        requires_o1_handling: bool = False,
        streaming_stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a message to the conversation context with metadata and token management.

        Args:
            chat_id (str): The unique identifier for the chat session.
            role (str): The role of the message sender ("user", "assistant", or "system").
            content (str): The message content to add.
            model_max_tokens (Optional[int]): The maximum number of tokens allowed for the model.
            requires_o1_handling (bool): Whether the message requires o1-preview handling.

        Raises:
            Exception: If there's an error adding the message to the database.
        """
        # Use default token limits if not provided
        if model_max_tokens is None:
            model_max_tokens = (
                self.MAX_MESSAGE_TOKENS if requires_o1_handling else self.MAX_TOKENS
            )

        # Calculate tokens and prepare metadata
        tokens = count_tokens(content, self.MODEL_NAME)
        metadata: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_count": tokens,
            "requires_o1": requires_o1_handling,
            "model_max_tokens": model_max_tokens,
        }

        # Add streaming stats if provided
        if streaming_stats:
            metadata["streaming"] = True
            metadata["streaming_stats"] = streaming_stats

        # Add message using Chat model
        Chat.add_message(
            chat_id=chat_id,
            role=role,
            content=content,
            metadata=metadata,
        )

        # Manage context window
        self._manage_context_window(chat_id, model_max_tokens)

    def _manage_context_window(self, chat_id: str, max_tokens: int) -> None:
        """
        Manage context window to stay within token limits.

        Args:
            chat_id (str): The chat ID to manage context for.
            max_tokens (int): Maximum tokens allowed.
        """
        messages = Chat.get_messages(chat_id)
        current_tokens = 0
        messages_to_keep: List[Dict[str, Any]] = []

        # Calculate tokens from newest to oldest
        for msg in reversed(messages):
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict):
                msg_tokens = metadata.get("token_count", 0)
                if (
                    isinstance(msg_tokens, (int, float))
                    and current_tokens + msg_tokens <= max_tokens
                ):
                    messages_to_keep.append(msg)
                    current_tokens += msg_tokens
                else:
                    break

        # If we need to remove messages
        if len(messages_to_keep) < len(messages):
            keep_ids = [
                msg["id"] for msg in messages_to_keep if isinstance(msg.get("id"), int)
            ]
            self._remove_old_messages(chat_id, keep_ids)

    def _remove_old_messages(self, chat_id: str, keep_ids: List[int]) -> None:
        """
        Remove old messages while keeping specified ones.

        Args:
            chat_id (str): The chat ID to remove messages from.
            keep_ids (List[int]): List of message IDs to keep.
        """
        if not keep_ids:
            return

        with db_session() as session:
            try:
                # Create placeholders for the IN clause
                placeholders = ",".join(f":id{i}" for i in range(len(keep_ids)))

                query = text(
                    f"""
                    DELETE FROM messages
                    WHERE chat_id = :chat_id
                    AND id NOT IN ({placeholders})
                """
                )

                # Create parameters dict with individual id bindings
                params = {"chat_id": chat_id}
                params.update({f"id{i}": id_val for i, id_val in enumerate(keep_ids)})

                session.execute(query, params)
                session.commit()
            except Exception as e:
                logger.error(f"Error removing old messages from chat {chat_id}: {e}")
                raise

    def get_usage_stats(self, chat_id: str) -> Dict[str, Any]:
        """
        Get detailed usage statistics.

        Args:
            chat_id (str): The chat ID to get stats for.

        Returns:
            Dict[str, Any]: Dictionary containing detailed usage statistics.
        """
        messages = Chat.get_messages(chat_id, include_system=True)

        stats = {
            "total_messages": len(messages),
            "total_tokens": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "system_messages": 0,
            "token_breakdown": {
                "user": 0,
                "assistant": 0,
                "system": 0,
            },
            "average_tokens_per_message": 0,
            "largest_message": {
                "role": None,
                "tokens": 0,
            },
        }

        for msg in messages:
            role = msg.get("role", "")
            metadata = msg.get("metadata", {})

            if isinstance(metadata, dict):
                tokens = metadata.get("token_count", 0)
                if isinstance(tokens, (int, float)):
                    tokens = int(tokens)
                    stats["total_tokens"] += tokens
                    if role in stats["token_breakdown"]:
                        stats["token_breakdown"][role] += tokens

                    # Track largest message
                    if tokens > stats["largest_message"]["tokens"]:
                        stats["largest_message"] = {
                            "role": role,
                            "tokens": tokens,
                        }

            if isinstance(role, str) and role in ["user", "assistant", "system"]:
                stats[f"{role}_messages"] += 1

        # Calculate average tokens per message
        if stats["total_messages"] > 0:
            stats["average_tokens_per_message"] = (
                stats["total_tokens"] / stats["total_messages"]
            )

        return stats


# Export an instance of ConversationManager
conversation_manager = ConversationManager()