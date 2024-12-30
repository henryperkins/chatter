import logging
from typing import Dict, List
from database import get_db


logger = logging.getLogger(__name__)


class ConversationManager:
    def __init__(self):
        self.chat_contexts: Dict[str, List[Dict[str, str]]] = {}

    def get_context(self, chat_id: str) -> List[Dict[str, str]]:
        """Get conversation context for a specific chat ID."""
        db = get_db()
        messages = db.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp",
            (chat_id,),
        ).fetchall()
        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    def add_message(self, chat_id: str, role: str, content: str) -> None:
        """Add a message to the conversation context."""
        db = get_db()
        db.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        db.commit()
        logger.debug(
            f"Added message to chat {chat_id}: "
            f"{role}: {content[:50]}..."
        )

    def clear_context(self, chat_id: str) -> None:
        """Clear conversation context for a specific chat ID."""
        db = get_db()
        db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        db.commit()
        logger.debug(f"Cleared context for chat {chat_id}")

    def trim_context(self, chat_id: str, max_messages: int = 10) -> None:
        """Trim conversation context to maintain maximum message count."""
        db = get_db()
        messages = db.execute(
            "SELECT id FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT -1 OFFSET ?",
            (chat_id, max_messages),
        ).fetchall()
        if messages:
            message_ids = [msg["id"] for msg in messages]
            db.execute(
                "DELETE FROM messages WHERE id IN ({})".format(
                    ",".join("?" * len(message_ids))
                ),
                message_ids,
            )
            db.commit()
            logger.debug(
                f"Trimmed context for chat {chat_id} "
                f"to {max_messages} messages"
            )
