import logging
import os
from typing import Dict, List
import tiktoken
from database import db_connection  # Use the centralized context manager

logger = logging.getLogger(__name__)

# Configurable Environment Variables (with defaults)
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "20"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "3500"))
MAX_MESSAGE_TOKENS = int(os.getenv("MAX_MESSAGE_TOKENS", "500"))
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")  # Model for tiktoken

def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string using tiktoken."""
    try:
        encoding = tiktoken.encoding_for_model(MODEL_NAME)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

class ConversationManager:
    """Manages conversations by storing and retrieving messages from the database."""

    def __init__(self):
        try:
            self.encoding = tiktoken.encoding_for_model(MODEL_NAME)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def calculate_total_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        Calculate the total number of tokens in the conversation, 
        accounting for the overhead tokens per message and start/end tokens.
        """
        total_tokens = 0
        for msg in messages:
            # ~4 tokens per message for role + formatting overhead
            total_tokens += 4
            total_tokens += count_tokens(msg["content"])

        # ~2 tokens for start and end of conversation overhead
        total_tokens += 2
        return total_tokens

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
        # We subtract 4 tokens to account for overhead in the message
        # if you want to be extra conservative.
        content = self.truncate_message(content, max_tokens=MAX_MESSAGE_TOKENS)

        with db_connection() as db:
            db.execute(
                "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content),
            )
            self.trim_context(chat_id)
            logger.debug(f"Added message to chat {chat_id}: {role}: {content[:50]}...")

    def clear_context(self, chat_id: str) -> None:
        """Clear the conversation context for a specific chat ID."""
        with db_connection() as db:
            db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            logger.debug(f"Cleared context for chat {chat_id}")

    def trim_context(self, chat_id: str) -> None:
        """Trim the conversation context to stay within both message and token limits."""
        with db_connection() as db:
            messages = self.get_context(chat_id, include_system=True)

            # 1. Trim based on number of messages
            if len(messages) > MAX_MESSAGES:
                excess_messages = len(messages) - MAX_MESSAGES
                try:
                    db.execute(
                        """
                        DELETE FROM messages
                        WHERE id IN (
                            SELECT id FROM messages
                            WHERE chat_id = ?
                            ORDER BY timestamp ASC
                            LIMIT ?
                        )
                        """,
                        (chat_id, excess_messages),
                    )
                    # Reload messages since some have been deleted
                    messages = self.get_context(chat_id, include_system=True)
                except Exception as e:
                    logger.error(f"Error trimming messages for chat {chat_id}: {e}")
                    return

            # 2. Trim based on total token count
            total_tokens = self.calculate_total_tokens(messages)
            while total_tokens > MAX_TOKENS and messages:
                tokens_to_remove = total_tokens - MAX_TOKENS
                cumulative_tokens = 0
                messages_to_remove = []

                # Accumulate enough messages from the oldest until we've removed enough tokens
                for msg in messages:
                    # Overhead for each message: 4 tokens + content
                    msg_tokens = 4 + count_tokens(msg["content"])
                    cumulative_tokens += msg_tokens
                    messages_to_remove.append(msg["id"])
                    if cumulative_tokens >= tokens_to_remove:
                        break

                try:
                    placeholders = ",".join(["?"] * len(messages_to_remove))
                    query = f"DELETE FROM messages WHERE id IN ({placeholders})"
                    db.execute(query, messages_to_remove)

                    # Re-fetch and recalculate token count
                    messages = self.get_context(chat_id, include_system=True)
                    total_tokens = self.calculate_total_tokens(messages)
                except Exception as e:
                    logger.error(f"Error trimming tokens for chat {chat_id}: {e}")
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
        messages = self.get_context(chat_id, include_system=True)
        total_tokens = self.calculate_total_tokens(messages)
        return {
            "total_messages": len(messages),
            "total_tokens": total_tokens,
        }