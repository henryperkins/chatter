import logging
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Union, Any
from dataclasses import dataclass

from sqlalchemy import text, Column, String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from database import db_session
from .base import Base
from .model import Model

logger = logging.getLogger(__name__)

# Removed ChatDTO entirely; transitioning its functionality into the Chat model.


class Chat(Base):
    """
    SQLAlchemy model representing the 'chats' table, enabling ORM relationships.
    """

    __tablename__ = "chats"

    id = Column(String, primary_key=True)  # Keep database column name as 'id'
    user_id = Column(Integer, nullable=False)
    title = Column(String, default="New Chat")
    model_id = Column(Integer, ForeignKey("models.id"), nullable=True)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), 
                       nullable=False,
                       server_default=text('CURRENT_TIMESTAMP'),
                       default=datetime.utcnow)

    # Relationships
    model = relationship("Model", back_populates="chats", lazy="joined")
    files = relationship("UploadedFile", back_populates="chat")

    def __repr__(self):
        return f"<Chat(id={self.id}, user_id={self.user_id}, title='{self.title}', model_id={self.model_id})>"

    @classmethod
    def get_by_id(cls, chat_id: str) -> Optional["Chat"]:
        """
        Retrieve a Chat instance by primary key using ORM.
        """
        with db_session() as db:
            return db.query(cls).filter(cls.id == chat_id, cls.is_deleted == False).first()

    @classmethod
    def is_chat_owned_by_user(cls, chat_id: str, user_id: int) -> bool:
        """
        Check whether the specified user is the owner of the given chat via ORM.
        """
        chat = cls.get_by_id(chat_id)
        return bool(chat and chat.user_id == user_id)

    @classmethod
    def can_access_chat(cls, chat_id: str, user_id: int, user_role: str) -> bool:
        """
        Check if a user can access a chat based on ownership and role.
        Admin users can access all chats; regular users only their own chats.
        """
        if user_role == "admin":
            with db_session() as db:
                # Ensure chat even exists (not deleted)
                chat_exists = db.query(cls).filter(cls.id == chat_id, cls.is_deleted == False).count()
                return bool(chat_exists)
        else:
            return cls.is_chat_owned_by_user(chat_id, user_id)

    @classmethod
    def is_title_default(cls, chat_id: str) -> bool:
        """
        Check whether a chat has the default title.
        """
        chat_obj = cls.get_by_id(chat_id)
        if not chat_obj:
            return False
        return bool(chat_obj and chat_obj.title == "New Chat")

    @classmethod
    def update_model(cls, chat_id: str, model_id: int) -> None:
        """
        Update the model associated with the given chat via text query (or ORM).
        Here we use text query for demonstration, but you could do it via ORM as well.
        """
        try:
            with db_session() as db:
                stmt = text("""
                    UPDATE chats
                    SET model_id = :model_id
                    WHERE id = :id
                """)
                db.execute(stmt, {"chat_id": chat_id, "model_id": model_id})
                db.commit()
            logger.info(f"Updated model to {model_id} for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to update chat model: {e}")
            raise

    @classmethod
    def update_model_id(cls, chat_id: str, model_id: int) -> None:
        """
        Same as update_model, but preserved for backward naming usage.
        """
        cls.update_model(chat_id, model_id)

    @classmethod
    def update_title(cls, chat_id: str, title: str) -> None:
        """
        Update the title of a chat with validation,
        preventing empty titles and ensuring we store only up to 50 characters.
        """
        cleaned_title = title.strip()[:50]
        if not cleaned_title:
            raise ValueError("Chat title cannot be empty.")

        try:
            with db_session() as db:
                stmt = text("""
                    UPDATE chats
                    SET title = :title
                    WHERE id = :id
                """)
                db.execute(stmt, {"title": cleaned_title, "chat_id": chat_id})
                db.commit()
            logger.info(f"Chat title updated for chat_id {chat_id} to '{cleaned_title}'")
        except Exception as e:
            logger.error(f"Failed to update chat title for chat_id {chat_id}: {e}")
            raise

    @classmethod
    def get_user_chats(cls, user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Union[str, int]]]:
        """
        Retrieve paginated chat history for a user with message counts and last activity.
        """
        try:
            with db_session() as db:
                query = text("""
                    SELECT
                        c.id, c.user_id, c.title, c.model_id,
                        c.created_at as created_at,
                        m.name as model_name,
                        COUNT(msg.id) as message_count,
                        MAX(msg.timestamp) as last_activity,
                        SUM(CASE WHEN msg.role = 'user' THEN 1 ELSE 0 END) as user_messages,
                        SUM(CASE WHEN msg.role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages
                    FROM chats c
                    LEFT JOIN models m ON c.model_id = m.id
                    LEFT JOIN messages msg ON c.id = msg.chat_id
                    WHERE c.user_id = :user_id
                    AND (c.is_deleted = FALSE OR c.is_deleted IS NULL)
                    GROUP BY c.id, c.user_id, c.title, c.model_id, c.created_at, m.name, c.created_at
                    ORDER by last_activity DESC NULLS LAST
                    LIMIT :limit OFFSET :offset
                """)
                rows = db.execute(query, {"user_id": user_id, "limit": limit, "offset": offset}).mappings().all()

            chats = []
            for row in rows:
                try:
                    created_at = row["created_at"].isoformat() if row["created_at"] else None
                    # Handle last_activity datetime conversion
                    if isinstance(row["last_activity"], datetime):
                        last_activity = row["last_activity"].isoformat()
                    else:
                        last_activity = str(row["last_activity"]) if row["last_activity"] else created_at
                except Exception as e:
                    logger.error(f"Error formatting timestamps: {e}")
                    created_at = None
                    last_activity = None

                chats.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "model_id": row["model_id"],
                    "model_name": row["model_name"] or "Unknown Model",
                    "created_at": created_at,
                    "message_count": row["message_count"] or 0,
                    "last_activity": last_activity,
                    "user_messages": row["user_messages"] or 0,
                    "assistant_messages": row["assistant_messages"] or 0
                })
            return chats
        except Exception as e:
            logger.error(f"Error retrieving chats for user_id {user_id}: {e}")
            raise

    @classmethod
    def get_default_model_id(cls) -> Optional[int]:
        """
        Retrieve the ID of the default model if available; fallback to any active model if none is default.
        """
        try:
            with db_session() as db:
                row = db.execute(text("""
                    SELECT m.id FROM models m 
                    JOIN providers p ON m.provider_id = p.id
                    WHERE m.is_default = TRUE 
                    AND p.is_active = TRUE
                    LIMIT 1
                """)).mappings().first()
                if row:
                    logger.debug(f"Default model ID retrieved: {row['id']}")
                    return row["id"]

                logger.warning("No default model found with active provider")

                row = db.execute(text("""
                    SELECT m.id FROM models m
                    JOIN providers p ON m.provider_id = p.id 
                    WHERE p.is_active = TRUE
                    LIMIT 1
                """)).mappings().first()
                if row:
                    logger.debug(f"Using model ID {row['id']} as fallback")
                    return row["id"]

                logger.error("No models available with active providers")
                return None
        except Exception as e:
            logger.error(f"Error retrieving default model ID: {e}")
            raise

    @classmethod
    def create(cls, id: str, user_id: int, title: str = "New Chat", model_id: Optional[int] = None) -> None:
        """Create a new chat with the given ID"""
        """
        Create a new chat record. Accepts an optional model_id or uses the default if none specified.
        """
        cleaned_title = title.strip()[:50]
        if model_id is None:
            model_id = cls.get_default_model_id()
            if model_id is None:
                raise ValueError("No default model available and no model_id provided")

        try:
            with db_session() as db:
                new_chat = cls(
                    id=id,
                    user_id=user_id,
                    title=cleaned_title,
                    model_id=model_id
                )
                db.add(new_chat)
                db.commit()
                logger.info(f"Chat created: {id} for user {user_id} with model {model_id or 'default'}")
        except Exception as e:
            logger.error(f"Failed to create chat {id}: {e}")
            raise

    @classmethod
    def soft_delete(cls, chat_id: str) -> None:
        """
        Mark a chat as deleted (is_deleted=TRUE) without removing the record.
        """
        try:
            with db_session() as db:
                stmt = text("""
                    UPDATE chats
                    SET is_deleted = TRUE
                    WHERE id = :id
                """)
                db.execute(stmt, {"chat_id": chat_id})
                db.commit()
            logger.info(f"Chat soft-deleted: {chat_id}")
        except Exception as e:
            logger.error(f"Failed to soft-delete chat {chat_id}: {e}")
            raise

    @classmethod
    def get_model(cls, chat_id: str) -> Optional["Model"]:
        """
        Retrieve the associated Model for a given chat, using the Chat's model_id via ORM.
        """
        from .model import Model  # Local import
        with db_session() as db:
            chat = db.query(cls).filter(cls.id == chat_id).first()
            if chat and chat.model:
                if chat.model.model_type == 'o1':
                    # Force Azure-specific settings
                    chat.model.api_version = '2025-01-01-preview'
                    chat.model.temperature = 1.0
                    chat.model.max_completion_tokens = 100000
                return chat.model
            return Model.get_default()

    @classmethod
    def add_message(cls, chat_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Add a message to the chat with optional metadata, returning the newly inserted message ID.
        """
        logger.debug("Adding message to chat %s - Role: %s, Content length: %d",
                     chat_id, role, len(content))
        try:
            with db_session() as db:
                stmt = text("""
                    INSERT INTO messages (chat_id, role, content, metadata, timestamp)
                    VALUES (:chat_id, :role, :content, :metadata, NOW())
                    RETURNING id
                """)
                result = db.execute(stmt, {
                    "chat_id": chat_id,
                    "role": role,
                    "content": content,
                    "metadata": json.dumps(metadata, default=str) if metadata is not None else '{}'
                })
                inserted_id = result.scalar()
                if inserted_id is None:
                    raise ValueError("No message ID returned from insert.")
                db.commit()
            logger.debug(f"Added message to chat {chat_id} with message_id {inserted_id}")
            return int(inserted_id)
        except Exception as e:
            logger.error(f"Error adding message to chat {chat_id}: {e}")
            raise

    @classmethod
    def get_messages(cls, chat_id: str, include_system: bool = False) -> List[Dict[str, Union[int, str, Dict[str, Any]]]]:
        """
        ORM approach to retrieve messages for a chat, optionally excluding system messages.
        """
        try:
            with db_session() as db:
                conditions = ["chat_id = :chat_id"]
                if not include_system:
                    conditions.append("role != 'system'")

                stmt = text(f"""
                    SELECT id, role, content, metadata, timestamp
                    FROM messages
                    WHERE {' AND '.join(conditions)}
                    ORDER BY timestamp ASC
                """)
                rows = db.execute(stmt, {"chat_id": chat_id}).mappings().all()

            messages = []
            for row in rows:
                msg = dict(row)
                # Convert metadata from JSON if needed
                if not isinstance(msg['metadata'], dict):
                    if msg['metadata']:
                        try:
                            msg['metadata'] = json.loads(msg['metadata'])
                        except Exception:
                            msg['metadata'] = {}
                    else:
                        msg['metadata'] = {}
                messages.append(msg)
            return messages
        except Exception as e:
            logger.error(f"Error getting messages for chat {chat_id}: {e}")
            raise
