import logging
from typing import Dict, List


logger = logging.getLogger(__name__)


class ConversationManager:
    def __init__(self):
        self.chat_contexts: Dict[str, List[Dict[str, str]]] = {}

    def get_context(self, chat_id: str) -> List[Dict[str, str]]:
        """Get conversation context for a specific chat ID."""
        return self.chat_contexts.get(chat_id, [])

    def add_message(self, chat_id: str, role: str, content: str) -> None:
        """Add a message to the conversation context."""
        if chat_id not in self.chat_contexts:
            self.chat_contexts[chat_id] = []
        self.chat_contexts[chat_id].append(
            {"role": role, "content": content}
        )
        logger.debug(
            f"Added message to chat {chat_id}: "
            f"{role}: {content[:50]}..."
        )

    def clear_context(self, chat_id: str) -> None:
        """Clear conversation context for a specific chat ID."""
        if chat_id in self.chat_contexts:
            del self.chat_contexts[chat_id]
            logger.debug(f"Cleared context for chat {chat_id}")

    def trim_context(self, chat_id: str, max_messages: int = 10) -> None:
        """Trim conversation context to maintain maximum message count."""
        if chat_id in self.chat_contexts:
            self.chat_contexts[chat_id] = self.chat_contexts[chat_id][
                -max_messages:
            ]
            logger.debug(
                f"Trimmed context for chat {chat_id} "
                f"to {max_messages} messages"
            )