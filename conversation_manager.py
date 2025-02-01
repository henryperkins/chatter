import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict
from token_utils import MessageDict

import tiktoken
from tiktoken import get_encoding
from sqlalchemy import text

from context_manager import ContextManager
from database import db_session
from logging_config import get_logger
from models.chat import Chat
from token_utils import (
    count_conversation_tokens,
    count_message_tokens,
)

# TypedDict for strict token breakdown fields
class TokenBreakdown(TypedDict):
    user: int
    assistant: int
    system: int


# Get loggers
logger = get_logger(__name__)
token_logger = get_logger("token_usage")

# Configurable Environment Variables (with defaults)
MAX_MESSAGES: int = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "32000"))  # Increased from 16384 to 32000
MAX_MESSAGE_TOKENS: int = int(os.getenv("MAX_MESSAGE_TOKENS", "32000"))  # Increased from 8192
MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4")  # Model for token counting

class ConversationManager:
    """
    Manages conversations by storing and retrieving messages from the database,
    handling token limits, and managing context windows.
    """

    def __init__(self) -> None:
        self.context_manager = ContextManager(MAX_TOKENS)
        # Cache each chat's "optimized" context if needed
        self.context_cache: Dict[str, List[Dict[str, Any]]] = {}

    def get_context(
        self,
        chat_id: str,
        include_system: bool = False
    ) -> List[Dict[str, str]]:
        """
        Retrieve the conversation context with proper formatting.

        Args:
            chat_id: The ID of the chat.
            include_system: Whether to include system messages.

        Returns:
            A list of message dictionaries containing role and content.
        """
        messages = Chat.get_messages(chat_id=chat_id, include_system=include_system)
        context: List[Dict[str, str]] = []

        # Always add markdown formatting request, even for models that don't use system messages
        markdown_request = {
            "role": "system" if include_system else "user",
            "content": "Format your responses using markdown for better readability. Use standard markdown syntax for headers (#), lists (- or 1.), emphasis (* or _), etc. For code blocks, specify the language after the opening triple backticks (e.g., ```python, ```javascript, ```sql) to enable syntax highlighting. Only use triple backticks to enclose code blocks - do not wrap the entire response in a code block."
        }
        context.append(markdown_request)

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if isinstance(role, str) and isinstance(content, str):
                context.append({"role": role, "content": content})

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
            chat_id: The ID of the chat.
            role: The role of the message (e.g., 'user', 'assistant', 'system').
            content: The message content.
            model_max_tokens: The maximum tokens the model can handle.
            requires_o1_handling: Flag for special handling (e.g., O1 transformations).
            streaming_stats: Optional dict containing streaming statistics.
        """
        # Extract file attachments if present in content
        file_attachments = []
        if "Attached files:" in content:
            parts = content.split("Attached files:", 1)
            main_content = parts[0].strip()
            attachments_text = parts[1].strip()

            # Parse file attachments
            current_file = {"name": "", "content": ""}
            for line in attachments_text.split('\n'):
                if line.startswith('[') and line.endswith(']:'):
                    # Save previous file if exists
                    if current_file["name"] and current_file["content"]:
                        file_attachments.append(current_file.copy())
                    # Start new file
                    current_file["name"] = line[1:-2]
                    current_file["content"] = ""
                else:
                    current_file["content"] += line + "\n"

            # Add last file
            if current_file["name"] and current_file["content"]:
                file_attachments.append(current_file)

            # Use main content for the message
            content = main_content

        message_obj = {"role": role, "content": content}
        tokens = count_message_tokens(message_obj)
        logger.debug("Calculated %d tokens for message: %s", tokens, message_obj)

        metadata: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_count": tokens,
            "requires_o1": requires_o1_handling,
            "model_max_tokens": model_max_tokens,
            "has_attachments": bool(file_attachments)
        }

        # Add file attachments to metadata if present
        if file_attachments:
            metadata["attachments"] = file_attachments
            logger.debug("Added %d file attachments to metadata", len(file_attachments))

        # Add streaming stats if provided
        if streaming_stats:
            metadata["streaming"] = True
            metadata["streaming_stats"] = streaming_stats
            logger.debug("Added streaming stats to metadata: %s", streaming_stats)

        logger.debug("Message metadata prepared: %s", metadata)

        # For assistant messages, store raw content
        if role == "assistant":
            metadata["raw_content"] = content

        # Truncate user message if it exceeds token limit
        if role == "user" and tokens > MAX_MESSAGE_TOKENS:
            content = self._truncate_content(content, get_encoding("cl100k_base"))
            metadata["truncated"] = True

        # Add message and get the new message ID
        message_id = Chat.add_message(
            chat_id=chat_id, role=role, content=content, metadata=metadata
        )

        # Lint the assistant's message after recording it
        if role == "assistant":
            self.lint_message(chat_id, message_id)

        # Manage context window
        self._manage_context_window(chat_id, model_max_tokens)

    def _truncate_content(self, content: str, encoding: Any) -> str:
        """
        Truncate content to fit within the token limit.

        Args:
            content: The original message content.
            encoding: The tiktoken encoding to use.

        Returns:
            The truncated content with a note appended.
        """
        tokens = encoding.encode(content)[:MAX_MESSAGE_TOKENS]
        truncated = encoding.decode(tokens)
        return f"{truncated}\n\n[Note: Content truncated to fit token limit]"

    def _manage_context_window(self, chat_id: str, max_tokens: Optional[int]) -> None:
        """
        Manage context window using advanced context management techniques.

        Args:
            chat_id: The ID of the chat.
            max_tokens: The maximum token limit for the model.
        """
        try:
            messages = Chat.get_messages(chat_id)
            logger.debug("Retrieved %d messages for chat %s", len(messages), chat_id)

            # Attempt to get an optimized context from context_manager
            if hasattr(self.context_manager, "get_context"):
                optimized_context = self.context_manager.get_context(messages)
            else:
                optimized_context = messages
                logger.warning(
                    "ContextManager.get_context not available, using full context"
                )

            # Process messages with attachments
            for msg in optimized_context:
                metadata = msg.get("metadata", {})
                if metadata.get("has_attachments"):
                    attachments = metadata.get("attachments", [])
                    if attachments:
                        # Reconstruct content with attachments
                        original_content = msg["content"]
                        attachment_text = "\n\nAttached files:\n"
                        for attachment in attachments:
                            attachment_text += f"\n[{attachment['name']}]:\n{attachment['content']}"

                        # Update message content
                        msg["content"] = original_content + attachment_text
                        logger.debug(
                            "Reconstructed message content with %d attachments",
                            len(attachments)
                        )

            current_tokens = count_conversation_tokens(optimized_context)

            # If messages were truncated, remove the excluded messages from the DB
            if len(optimized_context) < len(messages):
                keep_ids: List[int] = []
                for msg in optimized_context:
                    msg_id = msg.get("id")
                    if isinstance(msg_id, int):
                        keep_ids.append(msg_id)
                    elif isinstance(msg_id, str) and msg_id.isdigit():
                        keep_ids.append(int(msg_id))
                    else:
                        logger.warning("Invalid message ID type: %s", type(msg_id))
                self._remove_old_messages(chat_id, keep_ids)

            # Update context cache
            self.context_cache[chat_id] = optimized_context

            # Track token usage and optimize compression if available
            if hasattr(self.context_manager, "track_token_usage") and callable(getattr(self.context_manager, "track_token_usage")):
                self.context_manager.track_token_usage(current_tokens)  # type: ignore
            if hasattr(self.context_manager, "optimize_compression") and callable(getattr(self.context_manager, "optimize_compression")):
                self.context_manager.optimize_compression()  # type: ignore

        except Exception as e:
            logger.error("Error managing context window for chat %s: %s", chat_id, e)
            # Fallback to keeping all messages if an error occurs
            self.context_cache[chat_id] = Chat.get_messages(chat_id)

    def lint_message(self, chat_id: str, message_id: int) -> None:
        """
        Lint the message content and update it in the database if necessary.

        Args:
            chat_id: The ID of the chat.
            message_id: The ID of the message to lint.
        """
        logger.debug("Linting message %d in chat %s", message_id, chat_id)
        with db_session() as db:
            try:
                query = text(
                    """
                    SELECT content FROM messages
                    WHERE id = :message_id AND chat_id = :chat_id
                    """
                )
                result = (
                    db.execute(query, {"message_id": message_id, "chat_id": chat_id})
                    .mappings()
                    .first()
                )
                if result:
                    content = result["content"]
                    linted_content = self.perform_linting(content)
                    if linted_content != content:
                        update_query = text(
                            """
                            UPDATE messages
                            SET content = :content
                            WHERE id = :message_id
                            """
                        )
                        db.execute(
                            update_query, {"content": linted_content, "message_id": message_id}
                        )
                        db.commit()
                        logger.info(
                            "Message %d in chat %s was linted and updated",
                            message_id,
                            chat_id,
                        )
                    else:
                        logger.debug(
                            "No changes needed after linting message %d in chat %s",
                            message_id,
                            chat_id,
                        )
                else:
                    logger.error(
                        "Message with id %d not found in chat %s", message_id, chat_id
                    )
            except Exception as e:
                db.rollback()
                logger.error("Error linting message %d in chat %s: %s", message_id, chat_id, e)
                raise

    def perform_linting(self, content: str) -> str:
        """
        Perform linting on the message content.
        
        Args:
            content: The original message content.
        
        Returns:
            The linted message content.
        """
        # Fix code blocks and markdown formatting
        linted_content = self._fix_code_blocks(content)
        linted_content = self._fix_markdown_spacing(linted_content)
        return linted_content

    def _fix_code_blocks(self, content: str) -> str:
        """
        Fix code block formatting and ensure proper closure.
        """
        code_block_delimiter = "```"
        lines = content.split("\n")
        result = []
        in_code_block = False
        language = ""
        
        for line in lines:
            if line.startswith(code_block_delimiter):
                if not in_code_block:
                    # Starting a code block
                    in_code_block = True
                    # Extract language if specified
                    language = line[3:].strip()
                    # Add empty line before code block if needed
                    if result and result[-1].strip():
                        result.append("")
                    result.append(f"```{language}")
                else:
                    # Ending a code block
                    in_code_block = False
                    result.append("```")
                    # Add empty line after code block
                    result.append("")
            else:
                # Inside code block: preserve indentation
                if in_code_block:
                    result.append(line)
                else:
                    # Outside code block: normalize spacing
                    result.append(line.rstrip())
        
        # Close any unclosed code block
        if in_code_block:
            result.append("```")
            result.append("")
        
        return "\n".join(result).strip()

    def _fix_markdown_spacing(self, content: str) -> str:
        """
        Fix markdown spacing and formatting issues.
        """
        lines = content.split("\n")
        result = []
        prev_line_empty = True
        
        for line in lines:
            line = line.rstrip()
            
            # Skip multiple empty lines
            if not line:
                if not prev_line_empty:
                    result.append("")
                    prev_line_empty = True
                continue
            
            # Handle headers and lists
            if line.startswith(("#", "-", "*", "1.")):
                if not prev_line_empty:
                    result.append("")
                result.append(line)
                prev_line_empty = False
                continue
            
            result.append(line)
            prev_line_empty = False
        
        return "\n".join(result).strip()

    def _remove_old_messages(self, chat_id: str, keep_ids: List[int]) -> None:
        """
        Remove old messages while keeping specified ones.

        Args:
            chat_id: The ID of the chat.
            keep_ids: The IDs of messages to keep.
        """
        if not keep_ids:
            return

        try:
            with db_session() as db:
                query = text(
                    """
                    DELETE FROM messages
                    WHERE chat_id = :chat_id
                    AND id != ALL(:keep_ids)
                    """
                )
                db.execute(query, {"chat_id": chat_id, "keep_ids": keep_ids})
                db.commit()
        except Exception as e:
            logger.error("Error removing old messages from chat %s: %s", chat_id, e)
            raise

    def get_usage_stats(self, chat_id: str) -> Dict[str, Any]:
        """
        Get detailed usage statistics for a given chat.

        Args:
            chat_id: The ID of the chat.

        Returns:
            A dictionary containing various statistics about the conversation.
        """
        logger.debug("Getting usage stats for chat %s", chat_id)
        messages = Chat.get_messages(chat_id, include_system=True)
        logger.debug("Found %d messages for chat %s", len(messages), chat_id)

        # Use the TokenBreakdown TypedDict to ensure int values for user/assistant/system
        stats: Dict[str, Any] = {
            "total_messages": len(messages),
            "total_tokens": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "system_messages": 0,
            "token_breakdown": TokenBreakdown(user=0, assistant=0, system=0),
            "average_tokens_per_message": 0,
            "largest_message": {"role": None, "tokens": 0},
        }

        for msg in messages:
            role = msg.get("role", "")
            metadata: Dict[str, Any] = {}
            msg_metadata = msg.get("metadata")
            if isinstance(msg_metadata, dict):
                metadata = msg_metadata
            logger.debug("Processing message - Role: %s, Metadata: %s", role, metadata)

            # Safely extract token_count with proper type checking
            token_count = metadata.get("token_count")
            tokens = 0
            if isinstance(token_count, (int, float)):
                tokens = int(token_count)
            elif isinstance(token_count, str) and token_count.isdigit():
                tokens = int(token_count)
            else:
                logger.warning("Invalid token count in metadata: %s", token_count)
            if isinstance(tokens, (int, float)):
                tokens = int(tokens)
                if not isinstance(tokens, int):
                    logger.warning("Token count conversion failed for value: %s", tokens)
                    tokens = 0
                stats["total_tokens"] += tokens

                # Update token_breakdown only if role is recognized
                if role in stats["token_breakdown"]:
                    stats["token_breakdown"][role] += tokens
                    logger.debug(
                        "Added %d tokens to %s role (total: %d)",
                        tokens,
                        role,
                        stats["token_breakdown"][role],
                    )

                # Track largest message
                largest_tokens = stats["largest_message"]["tokens"]
                if isinstance(largest_tokens, int) and isinstance(tokens, int) and tokens > largest_tokens:
                    stats["largest_message"] = {"role": role, "tokens": tokens}
                    logger.debug("New largest message: %s with %d tokens", role, tokens)
            else:
                logger.warning(
                    "Invalid token count in metadata for message: %s", tokens
                )

            # Count messages by role
            if role in ["user", "assistant", "system"]:
                stats[f"{role}_messages"] += 1

        # Calculate average tokens per message
        if stats["total_messages"] > 0:
            stats["average_tokens_per_message"] = (
                stats["total_tokens"] / stats["total_messages"]
            )

        logger.debug("Final stats for chat %s: %s", chat_id, stats)
        return stats

# Export an instance of ConversationManager
conversation_manager = ConversationManager()
