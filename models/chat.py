import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Union

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
                    WHERE id = :chat_id AND user_id = :user_id
                """
                )
                chat = db.execute(
                    query, {"chat_id": chat_id, "user_id": user_id}
                ).fetchone()
                ownership = chat is not None
                logger.debug(
                    f"Ownership check for chat_id {chat_id} and user_id {user_id}: {ownership}"
                )
                return ownership
            except Exception as e:
                logger.error(f"Error checking ownership for chat_id {chat_id}: {e}")
                raise

    @staticmethod
    def is_title_default(chat_id: str) -> bool:
        """
        Check whether a chat has the default title.
        """
        with db_session() as db:
            try:
                query = text("SELECT title FROM chats WHERE id = :chat_id")
                row = db.execute(query, {"chat_id": chat_id}).mappings().first()
                is_default = bool(row) and row["title"] == "New Chat"
                logger.debug(f"Title default check for chat_id {chat_id}: {is_default}")
                return is_default
            except Exception as e:
                logger.error(f"Error checking title for chat_id {chat_id}: {e}")
                raise

    @staticmethod
    def update_title(chat_id: str, new_title: str) -> None:
        """
        Update the title of a chat with validation.
        """
        if not new_title.strip():
            raise ValueError("Chat title cannot be empty.")
        new_title = new_title.strip()[:50]  # Limit to 50 characters

        with db_session() as db:
            try:
                query = text(
                    """
                    UPDATE chats 
                    SET title = :title 
                    WHERE id = :chat_id
                """
                )
                db.execute(query, {"title": new_title, "chat_id": chat_id})
                db.commit()
                logger.info(
                    f"Chat title updated for chat_id {chat_id} to '{new_title}'"
                )
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update chat title for chat_id {chat_id}: {e}")
                raise

    @staticmethod
    def get_user_chats(
        user_id: int, limit: int = 10, offset: int = 0
    ) -> List[Dict[str, Union[str, int]]]:
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
                    ORDER by c.created_at DESC
                    LIMIT :limit OFFSET :offset
                """
                )
                chats = (
                    db.execute(
                        query, {"user_id": user_id, "limit": limit, "offset": offset}
                    )
                    .mappings()
                    .all()
                )

                from datetime import datetime

                chat_list = []

                for chat in chats:
                    chat_dict = {
                        "id": chat["id"],
                        "user_id": chat["user_id"],
                        "title": chat["title"],
                        "model_id": chat["model_id"],
                        "model_name": (
                            chat["model_name"]
                            if chat["model_name"]
                            else "Unknown Model"
                        ),
                        "timestamp": (
                            datetime.strptime(chat["timestamp"], "%Y-%m-%d %H:%M:%S")
                            if chat["timestamp"]
                            else None
                        ),
                    }
                    chat_list.append(chat_dict)

                logger.debug(f"Retrieved {len(chat_list)} chats for user_id {user_id}")
                return chat_list

            except Exception as e:
                logger.error(f"Error retrieving chats for user_id {user_id}: {e}")
                raise

    @staticmethod
    def get_by_id(chat_id: str) -> Optional["Chat"]:
        """
        Retrieve a chat by its ID.
        """
        with db_session() as db:
            try:
                query = text("SELECT id, user_id, title, model_id FROM chats WHERE id = :chat_id")
                row = db.execute(query, {"chat_id": chat_id}).mappings().first()
                if row:
                    chat_dict = dict(row)
                    return Chat(**chat_dict)
                return None
            except Exception as e:
                logger.error(f"Error retrieving chat by ID {chat_id}: {e}")
                raise

    @staticmethod
    def get_default_model_id() -> Optional[int]:
        """Get the ID of the default model."""
        with db_session() as db:
            try:
                query = text("SELECT id FROM models WHERE is_default = :is_default")
                row = db.execute(query, {"is_default": True}).mappings().first()
                model_id = row["id"] if row else None
                logger.debug(f"Default model ID: {model_id}")
                return model_id
            except Exception as e:
                logger.error(f"Error getting default model ID: {e}")
                raise

    @staticmethod
    def create(
        chat_id: str,
        user_id: int,
        title: str = "New Chat",
        model_id: Optional[int] = None,
    ) -> None:
        """Create a new chat record."""
        if len(title) > 50:
            title = title[:50]

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
                db.execute(
                    query,
                    {
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "title": title,
                        "model_id": model_id,
                    },
                )
                db.commit()
                logger.info(
                    f"Chat created: {chat_id} for user {user_id} with model {model_id or 'default'}"
                )
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create chat {chat_id}: {e}")
                raise

    @staticmethod
    def delete(chat_id: str) -> None:
        """
        Delete a chat and its associated messages efficiently.
        """
        with db_session() as db:
            try:
                pragma_query = text("PRAGMA foreign_keys = ON;")
                db.execute(pragma_query)

                delete_query = text("DELETE FROM chats WHERE id = :chat_id")
                db.execute(delete_query, {"chat_id": chat_id})
                db.commit()
                logger.info(f"Chat deleted: {chat_id}")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to delete chat {chat_id}: {e}")
                raise

    @staticmethod
    def get_model(chat_id: str) -> Optional["Model"]:
        """
        Retrieve the model object associated with a given chat.

        Args:
            chat_id: The chat's unique identifier

        Returns:
            Optional[Model]: The associated model object or None
        """
        from .model import Model  # Import here to avoid circular imports

        with db_session() as db:
            try:
                query = text("SELECT model_id FROM chats WHERE id = :chat_id")
                row = db.execute(query, {"chat_id": chat_id}).mappings().first()
                model_id = row["model_id"] if row else None

                logger.debug(f"Model ID for chat_id {chat_id}: {model_id}")

                if model_id:
                    model = Model.get_by_id(model_id)
                    return model
                return None

            except Exception as e:
                logger.error(f"Error retrieving model for chat_id {chat_id}: {e}")
                raise
