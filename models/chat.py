import logging
import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Union, Any

from sqlalchemy import text

from .base import db_session
from .model import Model  # Import at top level for type hints

logger = logging.getLogger(__name__)


@dataclass
class Chat:
    """
    Represents a chat session in the system.
    """
    id: str
    user_id: int
    title: str = "New Chat"
    model_id: Optional[int] = None

    def __post_init__(self):
        """Ensure user_id is an integer."""
        self.user_id = int(self.user_id)

    @staticmethod
    def is_chat_owned_by_user(chat_id: str, user_id: int) -> bool:
        """
        Verify that the chat belongs to the specified user.
        """
        with db_session() as db:
            try:
                query = text(
                    """
                    SELECT id FROM chats
                    WHERE id = :chat_id
                    AND user_id = :user_id
                    AND (is_deleted = 0 OR is_deleted IS NULL)
                    """
                )
                chat = db.execute(query, {"chat_id": chat_id, "user_id": user_id}).fetchone()
                ownership = chat is not None
                logger.debug(f"Ownership check for chat_id {chat_id} and user_id {user_id}: {ownership}")
                return ownership
            except Exception as e:
                logger.error(f"Error checking ownership for chat_id {chat_id}: {e}")
                raise

    @staticmethod
    def can_access_chat(chat_id: str, user_id: int, user_role: str) -> bool:
        """
        Check if a user can access a chat based on ownership and role.
        Admin users can access all chats.
        Regular users can only access their own chats.
        """
        if user_role == "admin":
            try:
                with db_session() as db:
                    query = text("SELECT COUNT(1) FROM chats WHERE id = :chat_id AND (is_deleted = 0 OR is_deleted IS NULL)")
                    result = db.execute(query, {"chat_id": chat_id}).scalar() or 0
                    exists = bool(result)
                    logger.debug(f"Admin access check for chat_id {chat_id}: {exists}")
                    return exists
            except Exception as e:
                logger.error(f"Error checking chat existence for chat_id {chat_id}: {e}")
                raise
        else:
            return Chat.is_chat_owned_by_user(chat_id, user_id)

    @staticmethod
    def is_title_default(chat_id: str) -> bool:
        """
        Check whether a chat has the default title.
        """
        with db_session() as db:
            try:
                query = text("SELECT title FROM chats WHERE id = :chat_id AND (is_deleted = 0 OR is_deleted IS NULL)")
                row = db.execute(query, {"chat_id": chat_id}).mappings().first()
                is_default = bool(row) and row["title"] == "New Chat"
                logger.debug(f"Title default check for chat_id {chat_id}: {is_default}")
                return is_default
            except Exception as e:
                logger.error(f"Error checking title for chat_id {chat_id}: {e}")
                raise

    @staticmethod
    def update_title(chat_id: str, title: str) -> None:
        """
        Update the title of a chat with validation.

        Args:
            chat_id: The ID of the chat to update
            title: The new title for the chat

        Raises:
            ValueError: If the title is empty
        """
        # Validate and clean the title
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Chat title cannot be empty.")

        # Truncate if necessary
        cleaned_title = cleaned_title[:50]

        with db_session() as db:
            try:
                query = text(
                    """
                    UPDATE chats
                    SET title = :title
                    WHERE id = :chat_id
                    """
                )
                db.execute(query, {"title": cleaned_title, "chat_id": chat_id})
                db.commit()
                logger.info(f"Chat title updated for chat_id {chat_id} to '{cleaned_title}'")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update chat title for chat_id {chat_id}: {e}")
                raise

    @staticmethod
    def get_user_chats(user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Union[str, int]]]:
        """
        Retrieve paginated chat history for a user.
        """
        with db_session() as db:
            try:
                query = text(
                    """
                    SELECT
                        c.id, c.user_id, c.title, c.model_id,
                        strftime('%Y-%m-%d %H:%M:%S', c.created_at) as timestamp,
                        m.name as model_name
                    FROM chats c
                    LEFT JOIN models m ON c.model_id = m.id
                    WHERE c.user_id = :user_id
                    AND (c.is_deleted = 0 OR c.is_deleted IS NULL)
                    ORDER by c.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                )
                chats = db.execute(query, {"user_id": user_id, "limit": limit, "offset": offset}).mappings().all()

                return [
                    {
                        "id": chat["id"],
                        "user_id": chat["user_id"],
                        "title": chat["title"],
                        "model_id": chat["model_id"],
                        "model_name": chat["model_name"] or "Unknown Model",
                        "timestamp": chat["timestamp"],
                    }
                    for chat in chats
                ]
            except Exception as e:
                logger.error(f"Error retrieving chats for user_id {user_id}: {e}")
                raise

    @staticmethod
    def get_default_model_id() -> Optional[int]:
        """
        Retrieve the ID of the default model.
        """
        with db_session() as db:
            try:
                query = text("SELECT id FROM models WHERE is_default = 1 LIMIT 1")
                row = db.execute(query).mappings().first()
                if row:
                    logger.debug(f"Default model ID retrieved: {row['id']}")
                    return row["id"]
                logger.warning("No default model found.")
                return None
            except Exception as e:
                logger.error(f"Error retrieving default model ID: {e}")
                raise

    @staticmethod
    def create(chat_id: str, user_id: int, title: str = "New Chat", model_id: Optional[int] = None) -> None:
        """
        Create a new chat record.

        Args:
            chat_id: Unique identifier for the chat
            user_id: ID of the user creating the chat
            title: Title of the chat (default: "New Chat")
            model_id: Optional ID of the model to use
        """
        # Validate and clean the title
        cleaned_title = title.strip()[:50]

        # Get default model if no model specified
        if model_id is None:
            model_id = Chat.get_default_model_id()

        with db_session() as db:
            try:
                query = text(
                    """
                    INSERT INTO chats (id, user_id, title, model_id)
                    VALUES (:chat_id, :user_id, :title, :model_id)
                    """
                )
                db.execute(query, {"chat_id": chat_id, "user_id": user_id, "title": cleaned_title, "model_id": model_id})
                db.commit()
                logger.info(f"Chat created: {chat_id} for user {user_id} with model {model_id or 'default'}")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create chat {chat_id}: {e}")
                raise

    @staticmethod
    def soft_delete(chat_id: str) -> None:
        """
        Soft-delete a chat by marking it as deleted.
        """
        with db_session() as db:
            try:
                query = text(
                    """
                    UPDATE chats
                    SET is_deleted = 1
                    WHERE id = :chat_id
                    """
                )
                db.execute(query, {"chat_id": chat_id})
                db.commit()
                logger.info(f"Chat soft-deleted: {chat_id}")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to soft-delete chat {chat_id}: {e}")
                raise

    @staticmethod
    def get_by_id(chat_id: str) -> Optional["Chat"]:
        """
        Retrieve a chat by its ID.
        """
        with db_session() as db:
            try:
                query = text("SELECT id, user_id, title, model_id FROM chats WHERE id = :chat_id AND (is_deleted = 0 OR is_deleted IS NULL)")
                row = db.execute(query, {"chat_id": chat_id}).mappings().first()
                return Chat(**row) if row else None
            except Exception as e:
                logger.error(f"Error retrieving chat by ID {chat_id}: {e}")
                raise

    @staticmethod
    def get_model(chat_id: str) -> Optional["Model"]:
        """
        Retrieve the model object associated with a given chat.
        """
        with db_session() as db:
            try:
                query = text("SELECT model_id FROM chats WHERE id = :chat_id AND (is_deleted = 0 OR is_deleted IS NULL)")
                row = db.execute(query, {"chat_id": chat_id}).mappings().first()
                if row and row["model_id"]:
                    return Model.get_by_id(row["model_id"])
                return None
            except Exception as e:
                logger.error(f"Error retrieving model for chat_id {chat_id}: {e}")
                raise

    @staticmethod
    def add_message(chat_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a message to the chat with optional metadata.

        Args:
            chat_id: The ID of the chat to add the message to
            role: The role of the message sender ('user', 'assistant', or 'system')
            content: The content of the message
            metadata: Optional metadata dictionary for the message
        """
        with db_session() as db:
            try:
                query = text("""
                    INSERT INTO messages (chat_id, role, content, metadata)
                    VALUES (:chat_id, :role, :content, :metadata)
                """)

                db.execute(query, {
                    "chat_id": chat_id,
                    "role": role,
                    "content": content,
                    "metadata": json.dumps(metadata or {})
                })
                db.commit()
                logger.info(f"Added message to chat {chat_id}")
            except Exception as e:
                db.rollback()
                logger.error(f"Error adding message to chat {chat_id}: {e}")
                raise

    @staticmethod
    def get_messages(chat_id: str, include_system: bool = False) -> List[Dict[str, Union[int, str, Dict[str, Any]]]]:
        """
        Get messages for a chat with optional filtering.

        Args:
            chat_id: The ID of the chat to get messages for
            include_system: Whether to include system messages in the result

        Returns:
            List of message dictionaries containing id, role, content, metadata, and timestamp
        """
        with db_session() as db:
            try:
                conditions = ["chat_id = :chat_id"]
                if not include_system:
                    conditions.append("role != 'system'")

                query = text(f"""
                    SELECT id, role, content, metadata,
                           strftime('%Y-%m-%d %H:%M:%S', timestamp) as timestamp
                    FROM messages
                    WHERE {' AND '.join(conditions)}
                    ORDER BY timestamp ASC
                """)

                result = db.execute(query, {"chat_id": chat_id}).mappings().all()
                messages: List[Dict[str, Union[int, str, Dict[str, Any]]]] = []
                for row in result:
                    message = dict(row)
                    try:
                        message['metadata'] = json.loads(message['metadata']) if message['metadata'] else {}
                    except (json.JSONDecodeError, TypeError):
                        message['metadata'] = {}
                    messages.append(message)
                return messages
            except Exception as e:
                logger.error(f"Error getting messages for chat {chat_id}: {e}")
                raise
