"""Module for managing chat conversations and context."""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

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
from expansions.search_expander import SearchExpander

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
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16384"))
MAX_MESSAGE_TOKENS: int = int(os.getenv("MAX_MESSAGE_TOKENS", "8192"))
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
        self.search_expander = SearchExpander()

    def _process_attachments(self, content: str) -> str:
        """
        Stub for processing attachments. 
        For now, just return the content unmodified.
        """
        return content

    def _add_file_messages(self, chat_id: str, file_content: str) -> None:
        """
        Stub method for adding file messages to the conversation.
        In a real scenario, we might parse file_content into one or more Chat messages.
        """
        logger.debug(f"Stub: add_file_messages for chat {chat_id}, content length {len(file_content)}.")

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
        logger.debug(f"Getting messages for chat_id: {chat_id}")
        messages = Chat.get_messages(chat_id=chat_id, include_system=include_system)
        logger.debug(f"Retrieved {len(messages)} messages for chat {chat_id}")
        context: List[Dict[str, str]] = []

        # Check if it's an O-series model
        chat = Chat.get_by_id(chat_id)
        model = Chat.get_model(chat_id) if chat else None
        is_o_series = model and getattr(model, "model_type", "").lower() in ["o3-mini", "o1", "o1-mini", "o1-preview"]

        # Add special note for O-series if needed
        if is_o_series:
            from os import getenv
            developer_msg = getenv("DEVELOPER_MESSAGE", "Formatting re-enabled - please enclose code blocks with appropriate markdown tags.")
            markdown_request = {
                "role": "developer",
                "content": developer_msg
            }
            context.append(markdown_request)

        for msg in messages:
            if isinstance(msg, dict):
                metadata = msg.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                    
                role = msg.get("role")
                content = msg.get("content")
                if isinstance(role, str) and isinstance(content, str):
                    context.append({
                        "role": role,
                        "content": content,
                        "timestamp": str(metadata.get("timestamp", ""))
                    })

        return context

    async def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        model_max_tokens: Optional[int] = None,
        requires_o1_handling: bool = False,
        streaming_stats: Optional[Dict[str, Any]] = None,
        initial_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
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
        # Enhanced processing for attachments
        if kwargs.get('has_attachments'):
            file_content = self._process_attachments(content)
            self._add_file_messages(chat_id, file_content)
            file_attachments = []
        else:
            file_attachments = []
            if isinstance(content, str) and "Here are the contents of the uploaded files:" in content:
                # Keep the full content with attachments
                file_attachments = self._extract_file_attachments(content)
            # Build minimal metadata
            metadata = {
                "has_attachments": True,
                "attachments": file_attachments
            }

        message_obj = {"role": role, "content": content}
        tokens = count_message_tokens(message_obj)
        logger.debug("Calculated %d tokens for message: %s", tokens, message_obj)

        metadata: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc),
            "token_count": tokens,
            "requires_o1": requires_o1_handling,
            "model_max_tokens": model_max_tokens,
            "has_attachments": bool(file_attachments)
        }

        # Add streaming stats if provided
        if streaming_stats:
            metadata["streaming"] = True
            metadata["streaming_stats"] = streaming_stats
            logger.debug("Added streaming stats to metadata: %s", streaming_stats)

        logger.debug("Message metadata prepared: %s", metadata)

        # For assistant messages, store raw content
        if role == "assistant":
            metadata["raw_content"] = content

        # Enforce per-message token limit
        if role == "user" and tokens > MAX_MESSAGE_TOKENS:
            content = self._truncate_content(content, get_encoding("cl100k_base"))
            metadata["truncated"] = True

        # Save message
        message_id = Chat.add_message(
            chat_id=chat_id, role=role, content=content, metadata=metadata
        )

        # Lint if needed
        if role == "assistant":
            self.lint_message(chat_id, message_id)

        # Manage context window
        await self._manage_context_window(chat_id, model_max_tokens)

    def _extract_file_attachments(self, content: str) -> List[Dict[str, str]]:
        """
        Extract file attachments from message content.
        """
        file_attachments = []
        if "Here are the contents of the uploaded files:" in content:
            parts = content.split("Here are the contents of the uploaded files:", 1)
            attachments_text = parts[1].strip()

            current_file = {"name": "", "content": ""}
            for line in attachments_text.split('\n'):
                if line.startswith('[File:') and line.endswith(']'):
                    # Save old file, start new
                    if current_file["name"] and current_file["content"]:
                        file_attachments.append(current_file.copy())
                    current_file["name"] = line[7:-1]
                    current_file["content"] = ""
                else:
                    current_file["content"] += line + "\n"

            # Last file
            if current_file["name"] and current_file["content"]:
                file_attachments.append(current_file)

        return file_attachments

    def _truncate_content(self, content: str, encoding: Any) -> str:
        """
        Truncate content to fit within MAX_MESSAGE_TOKENS.
        """
        tokens = encoding.encode(content)[:MAX_MESSAGE_TOKENS]
        truncated = encoding.decode(tokens)
        return f"{truncated}\n\n[Note: Content truncated to fit token limit]"

    async def _manage_context_window(self, chat_id: str, max_tokens: Optional[int]) -> None:
        """
        Manage advanced context with partial retrieval if needed.
        """
        try:
            messages = Chat.get_messages(chat_id)
            logger.debug("Retrieved %d messages for chat %s", len(messages), chat_id)

            # Process user messages for semantic analysis and knowledge graph
            for msg in messages:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content", "")
                    if content and isinstance(content, str):
                        # Try to get search expansions
                        expansions = self.search_expander.expand(content)
                        if expansions:
                            logger.debug("Got expansions: %s", expansions[:200])
                            expansion_msg = {
                                "role": "system",
                                "content": f"[Search Expansions]\n{expansions}"
                            }
                            Chat.add_message(chat_id, "system", expansion_msg["content"])

                        # Note: Semantic analysis, knowledge graph, and embeddings functionality
                        # is currently disabled as the required components are not initialized
                        logger.debug("Skipping semantic analysis for message content: %s...", content[:100])

            if hasattr(self.context_manager, "get_context"):
                optimized_context = self.context_manager.get_context(messages)
            else:
                optimized_context = messages
                logger.warning("ContextManager.get_context unavailable, using all messages.")

            # Rebuild attachments
            for msg in optimized_context:
                if not isinstance(msg, dict):
                    continue
                metadata = msg.get("metadata", {})
                if not isinstance(metadata, dict):
                    continue

                if bool(metadata.get("has_attachments")):
                    attachments = metadata.get("attachments", [])
                    if not isinstance(attachments, list):
                        continue

                    original_content = str(msg.get("content", ""))
                    attachment_text = "\n\nAttached files:\n"
                    valid_attachments = [
                        a for a in attachments
                        if isinstance(a, dict) and "name" in a and "content" in a
                    ]
                    for attachment in valid_attachments:
                        attachment_text += f"\n[{attachment['name']}]:\n{attachment['content']}"

                    msg["content"] = original_content + attachment_text
                    logger.debug("Reconstructed content: now has attachments")

            current_tokens = count_conversation_tokens(optimized_context)

            # Handle any truncated messages
            if len(optimized_context) < len(messages):
                keep_ids: List[int] = []
                for m in optimized_context:
                    if not isinstance(m, dict):
                        continue
                    msg_id = m.get("id")
                    if isinstance(msg_id, int):
                        keep_ids.append(msg_id)
                    elif isinstance(msg_id, str) and msg_id.isdigit():
                        keep_ids.append(int(msg_id))
                if keep_ids:
                    self._remove_old_messages(chat_id, keep_ids)

            self.context_cache[chat_id] = optimized_context

        except Exception as e:
            logger.error("Error in _manage_context_window for chat %s: %s", chat_id, e)
            self.context_cache[chat_id] = Chat.get_messages(chat_id)

    def lint_message(self, chat_id: str, message_id: int) -> None:
        """
        Lint the content of an assistant message.
        """
        logger.debug("Linting message %d in chat %s", message_id, chat_id)
        with db_session() as db:
            try:
                query = text("""
                    SELECT content FROM messages
                    WHERE id = :message_id AND chat_id = :chat_id
                """)
                result = db.execute(query, {
                    "message_id": message_id,
                    "chat_id": chat_id
                }).mappings().first()
                if result:
                    content = result["content"]
                    new_content = self.perform_linting(content)
                    if new_content != content:
                        update_query = text("""
                            UPDATE messages
                            SET content = :new_content
                            WHERE id = :message_id
                        """)
                        db.execute(update_query, {"new_content": new_content, "message_id": message_id})
                        db.commit()
                        logger.info("Message %d in chat %s was linted", message_id, chat_id)
                else:
                    logger.error("Message id %d not found in chat %s", message_id, chat_id)
            except Exception as e:
                db.rollback()
                logger.error("Error linting message %d in chat %s: %s", message_id, chat_id, e)
                raise

    def perform_linting(self, content: str) -> str:
        """
        Perform basic linting on assistant's content.
        """
        # Just fix code blocks, spacing
        c = self._fix_code_blocks(content)
        c = self._fix_markdown_spacing(c)
        return c

    def _fix_code_blocks(self, content: str) -> str:
        """
        Ensure code blocks are properly enclosed.
        """
        code_block_delimiter = "```"
        lines = content.split("\n")
        result = []
        in_block = False
        language = ""

        for line in lines:
            if line.startswith(code_block_delimiter):
                if not in_block:
                    in_block = True
                    language = line[3:].strip()
                    if result and result[-1].strip():
                        result.append("")
                    result.append(f"```{language}")
                else:
                    in_block = False
                    result.append("```")
                    result.append("")
            else:
                if in_block:
                    result.append(line)
                else:
                    result.append(line.rstrip())

        if in_block:
            result.append("```")
            result.append("")

        return "\n".join(result).strip()

    def _fix_markdown_spacing(self, content: str) -> str:
        """
        Basic fix for markdown spacing & formatting.
        """
        lines = content.split("\n")
        res = []
        prev_empty = True

        for line in lines:
            line = line.rstrip()
            if not line:
                if not prev_empty:
                    res.append("")
                    prev_empty = True
                continue

            if line.startswith(("#", "-", "*", "1.")) and not prev_empty:
                res.append("")
            res.append(line)
            prev_empty = False

        return "\n".join(res).strip()

    def _remove_old_messages(self, chat_id: str, keep_ids: List[int]) -> None:
        """
        Remove messages not in keep_ids.
        """
        if not keep_ids:
            return

        try:
            with db_session() as db:
                query = text("""
                    DELETE FROM messages
                    WHERE chat_id = :chat_id
                    AND id NOT IN :keep_ids
                """)
                db.execute(query, {"chat_id": chat_id, "keep_ids": tuple(keep_ids)})
                db.commit()
        except Exception as e:
            logger.error("Error removing old messages in chat %s: %s", chat_id, e)
            raise

    def get_usage_stats(self, chat_id: str) -> Dict[str, Any]:
        """
        Return conversation usage stats (token usage, etc).
        """
        logger.debug("Collecting usage stats for chat %s", chat_id)
        messages = Chat.get_messages(chat_id, include_system=True)
        messages = [m for m in messages if isinstance(m, dict)]

        stats: Dict[str, Any] = {
            "total_messages": len(messages),
            "total_tokens": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "system_messages": 0,
            "token_breakdown": TokenBreakdown(user=0, assistant=0, system=0),
            "average_tokens_per_message": 0,
            "largest_message": {"role": "", "tokens": 0},
        }

        for m in messages:
            role = str(m.get("role", ""))
            meta = m.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}
            try:
                tok_count = int(meta.get("token_count", 0))
            except (ValueError, TypeError):
                tok_count = 0

            stats["total_tokens"] += tok_count
            if role in ["user", "assistant", "system"]:
                stats["token_breakdown"][role] += tok_count
                stats[f"{role}_messages"] += 1

                if tok_count > stats["largest_message"]["tokens"]:
                    stats["largest_message"] = {"role": role, "tokens": tok_count}

        if stats["total_messages"] > 0:
            stats["average_tokens_per_message"] = round(stats["total_tokens"] / stats["total_messages"])

        stats["model_limits"] = {
            "max_tokens": MAX_TOKENS,
            "max_message_tokens": MAX_MESSAGE_TOKENS,
            "tokens_left": max(0, MAX_TOKENS - stats["total_tokens"]),
            "tokens_used_percentage": round((stats["total_tokens"] / MAX_TOKENS * 100), 1) if MAX_TOKENS > 0 else 0
        }

        logger.debug("Stats for chat %s: %s", chat_id, stats)
        return stats


# Export an instance
conversation_manager = ConversationManager()

def incorporate_file_content(self, chat_id: str, file_id: int) -> None:
    from models.uploaded_file import UploadedFile
    file_record = UploadedFile.get_by_id(file_id)
    if file_record is None:
        logger.warning("No tokenized text found for file_id %d", file_id)
        return
    if file_record.tokenized_text is None or file_record.tokenized_text.strip() == "":
        logger.warning("No tokenized text found for file_id %d", file_id)
        return

    Chat.add_message(
        chat_id=chat_id,
        role="system",
        content=f"[FileContent]\n{file_record.tokenized_text}"
    )
