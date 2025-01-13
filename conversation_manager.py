import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

import tiktoken
from sqlalchemy import text
from database import get_db
from models.chat import Chat
from chat_utils import count_tokens

logger = logging.getLogger(__name__)

# Token-related constants
SYSTEM_TOKENS: int = 4  # Base tokens for system messages
USER_TOKENS: int = 4    # Base tokens for user messages
ASSISTANT_TOKENS: int = 4  # Base tokens for assistant messages

# Configurable Environment Variables (with defaults)
MAX_MESSAGES: int = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "32000"))  # Increased from 16384 to 32000
MAX_MESSAGE_TOKENS: int = int(os.getenv("MAX_MESSAGE_TOKENS", "32000"))  # Increased from 8192
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
        Returns the number of tokens used by a list of messages with improved accuracy.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.

        Returns:
            Total number of tokens used by the messages.
        """
        num_tokens = 0
        for message in messages:
            # Add role-specific base tokens
            if message["role"] == "system":
                num_tokens += SYSTEM_TOKENS
            elif message["role"] == "user":
                num_tokens += USER_TOKENS
            elif message["role"] == "assistant":
                num_tokens += ASSISTANT_TOKENS

            # Count content tokens
            content_tokens = count_tokens(message["content"], MODEL_NAME)
            num_tokens += content_tokens

            # Add to message metadata if available
            if isinstance(message.get("metadata"), dict):
                message["metadata"]["token_count"] = content_tokens

        return num_tokens

    def get_context(self, chat_id: str, include_system: bool = False) -> List[Dict[str, str]]:
        """
        Retrieve the conversation context with proper formatting.

        Args:
            chat_id: The unique identifier for the chat session.
            include_system: Whether to include system messages. Defaults to False.

        Returns:
            A list of message dictionaries with 'role' and 'content'.
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
            chat_id: The unique identifier for the chat session.
            role: The role of the message sender ("user", "assistant", or "system").
            content: The message content to add.
            model_max_tokens: The maximum number of tokens allowed for the model.
            requires_o1_handling: Whether the message requires o1-preview handling.

        Raises:
            Exception: If there's an error adding the message to the database.
        """
        try:
            encoding = tiktoken.encoding_for_model(MODEL_NAME)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        if model_max_tokens is None:
            if requires_o1_handling:
                model_max_tokens = MAX_MESSAGE_TOKENS  # Default for o1-preview
            else:
                model_max_tokens = MAX_TOKENS  # Default for other models

        """Add a message to the conversation with metadata and formatting."""
        try:
            encoding = tiktoken.encoding_for_model(MODEL_NAME)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        if model_max_tokens is None:
            model_max_tokens = MAX_TOKENS if not requires_o1_handling else MAX_MESSAGE_TOKENS

        # Calculate tokens and prepare metadata
        tokens = len(encoding.encode(content))
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

        # For assistant messages, store both raw and formatted content
        if role == "assistant":
            import markdown_it
            from bs4 import BeautifulSoup

            # Initialize markdown parser with your preferred configuration
            md = markdown_it.MarkdownIt('commonmark', {'html': True})

            # Convert markdown to HTML
            html_content = md.render(content)

            # Clean and format the HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            # Store both raw and formatted content in metadata
            metadata["raw_content"] = content
            metadata["formatted_content"] = str(soup)

            # Use formatted content for storage
            content = str(soup)

        if role == "user" and tokens > MAX_MESSAGE_TOKENS:
            content = self._truncate_content(content, encoding)
            metadata["truncated"] = True

        # Add message using Chat model
        Chat.add_message(
            chat_id=chat_id,
            role=role,
            content=content,
            metadata=metadata
        )

        # Manage context window
        self._manage_context_window(chat_id, model_max_tokens)

    def _truncate_content(self, content: str, encoding: Any) -> str:
        """
        Truncate content to fit within token limit.

        Args:
            content: The content to truncate
            encoding: The tiktoken encoding to use

        Returns:
            Truncated content with a note
        """
        tokens = encoding.encode(content)[:MAX_MESSAGE_TOKENS]
        truncated = encoding.decode(tokens)
        return f"{truncated}\n\n[Note: Content truncated to fit token limit]"

    def _manage_context_window(self, chat_id: str, max_tokens: int) -> None:
        """
        Manage context window to stay within token limits.

        Args:
            chat_id: The chat ID to manage context for
            max_tokens: Maximum tokens allowed
        """
        messages = Chat.get_messages(chat_id)
        current_tokens = 0
        messages_to_keep: List[Dict[str, Any]] = []

        # Calculate tokens from newest to oldest
        for msg in reversed(messages):
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict):
                msg_tokens = metadata.get("token_count", 0)
                if isinstance(msg_tokens, (int, float)) and current_tokens + msg_tokens <= max_tokens:
                    messages_to_keep.append(msg)
                    current_tokens += msg_tokens
                else:
                    break

        # If we need to remove messages
        if len(messages_to_keep) < len(messages):
            keep_ids = [msg["id"] for msg in messages_to_keep if isinstance(msg.get("id"), int)]
            self._remove_old_messages(chat_id, keep_ids)

    def _remove_old_messages(self, chat_id: str, keep_ids: List[int]) -> None:
        """
        Remove old messages while keeping specified ones.

        Args:
            chat_id: The chat ID to remove messages from
            keep_ids: List of message IDs to keep
        """
        if not keep_ids:
            return

        db = get_db()
        try:
            # Create placeholders for the IN clause
            placeholders = ','.join(f':id{i}' for i in range(len(keep_ids)))

            query = text(f"""
                DELETE FROM messages
                WHERE chat_id = :chat_id
                AND id NOT IN ({placeholders})
            """)

            # Create parameters dict with individual id bindings
            params = {"chat_id": chat_id}
            params.update({f"id{i}": id_val for i, id_val in enumerate(keep_ids)})

            db.execute(query, params)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error removing old messages from chat {chat_id}: {e}")
            raise
        finally:
            db.close()

    def get_usage_stats(self, chat_id: str) -> Dict[str, Any]:
        """
        Get detailed usage statistics.

        Args:
            chat_id: The chat ID to get stats for

        Returns:
            Dictionary containing detailed usage statistics
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
                "system": 0
            },
            "average_tokens_per_message": 0,
            "largest_message": {
                "role": None,
                "tokens": 0
            }
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
                            "tokens": tokens
                        }

            if isinstance(role, str) and role in ["user", "assistant", "system"]:
                stats[f"{role}_messages"] += 1

        # Calculate average tokens per message
        if stats["total_messages"] > 0:
            stats["average_tokens_per_message"] = stats["total_tokens"] / stats["total_messages"]

        return stats


# Export an instance of ConversationManager
conversation_manager = ConversationManager()
