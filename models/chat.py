import logging
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Union, Any, TYPE_CHECKING

from sqlalchemy import JSON, text, String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session

from .base import Base

if TYPE_CHECKING:
    # Only for type hints, avoids runtime import cycle
    from .model import Model

logger = logging.getLogger(__name__)

class Chat(Base):
    """
    SQLAlchemy model representing the 'chats' table, enabling ORM relationships.
    """

    __tablename__ = "chats"

    # Primary key and required fields (no defaults)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("models.id", ondelete="SET NULL"),
        nullable=True
    )

    # Fields with defaults
    title: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="New Chat"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text('CURRENT_TIMESTAMP'),
        default=datetime.utcnow
    )

    # Relationships
    model: Mapped[Optional["Model"]] = relationship(
        "Model",
        back_populates="chats",
        lazy="joined"
    )
    files = relationship(
        "UploadedFile",
        back_populates="chat",
        lazy="select"
    )

    def __init__(self, **kwargs) -> None:
        """Initialize a new Chat instance."""
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"<Chat(id={self.id}, user_id={self.user_id}, title='{self.title}', model_id={self.model_id})>"

    @classmethod
    def get_by_id(cls, session: Session, chat_id: str) -> Optional["Chat"]:
        """
        Retrieve a Chat instance by primary key using an existing Session.
        """
        return session.query(cls).filter(cls.id == chat_id, cls.is_deleted == False).first()

    @classmethod
    def is_chat_owned_by_user(cls, session: Session, chat_id: str, user_id: int) -> bool:
        """
        Check whether the specified user is the owner of the given chat via ORM.
        """
        chat = cls.get_by_id(session, chat_id)
        return bool(chat and chat.user_id == user_id)

    @classmethod
    def can_access_chat(cls, session: Session, chat_id: str, user_id: int, user_role: str) -> bool:
        """
        Check if a user can access a chat based on ownership and role.
        Admin users can access all chats; regular users only their own chats.
        """
        if user_role == "admin":
            # Ensure chat exists and is not deleted
            chat_exists = session.query(cls).filter(cls.id == chat_id, cls.is_deleted == False).count()
            return bool(chat_exists)
        else:
            # For non-admin, must own the chat
            return cls.is_chat_owned_by_user(session, chat_id, user_id)

    @classmethod
    def is_title_default(cls, session: Session, chat_id: str) -> bool:
        """
        Check whether a chat has the default title.
        """
        chat_obj = cls.get_by_id(session, chat_id)
        return bool(chat_obj and chat_obj.title == "New Chat")

    @classmethod
    def update_model(cls, session: Session, chat_id: str, model_id: int) -> None:
        """
        Update the model associated with the given chat via a prepared statement.
        """
        stmt = text("""
            UPDATE chats
            SET model_id = :model_id
            WHERE id = :chat_id
        """)
        session.execute(stmt, {"chat_id": chat_id, "model_id": model_id})
        session.commit()
        logger.info("Updated model to %s for chat %s", model_id, chat_id)

    @classmethod
    def update_model_id(cls, session: Session, chat_id: str, model_id: int) -> None:
        """
        Same as update_model, but preserved for backward compatibility in naming.
        """
        cls.update_model(session, chat_id, model_id)

    @classmethod
    def update_title(cls, session: Session, chat_id: str, title: str) -> None:
        """
        Update the title of a chat with validation,
        preventing empty titles and ensuring we store only up to 50 characters.
        """
        cleaned_title = title.strip()[:50]
        if not cleaned_title:
            raise ValueError("Chat title cannot be empty.")

        stmt = text("""
            UPDATE chats
            SET title = :title
            WHERE id = :chat_id
        """)
        session.execute(stmt, {"title": cleaned_title, "chat_id": chat_id})
        session.commit()
        logger.info("Chat title updated for chat_id %s to '%s'", chat_id, cleaned_title)

    @classmethod
    def get_user_chats(cls, session: Session, user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Union[str, int]]]:
        """
        Retrieve paginated chat history for a user with message counts and last activity.
        """
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
            GROUP BY c.id, c.user_id, c.title, c.model_id, c.created_at, m.name
            ORDER by last_activity DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """)
        rows = session.execute(query, {"user_id": user_id, "limit": limit, "offset": offset}).mappings().all()
        chats = []
        for row in rows:
            created_at = row["created_at"].isoformat() if row["created_at"] else None
            if isinstance(row["last_activity"], datetime):
                last_activity = row["last_activity"].isoformat()
            else:
                last_activity = str(row["last_activity"]) if row["last_activity"] else created_at

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

    @classmethod
    def get_default_model_id(cls, session: Session) -> Optional[int]:
        """
        Retrieve the ID of the default model if available; fallback to any active model if none is default.
        """
        # First try to get a default model with an active provider
        row = session.execute(text("""
            SELECT m.id FROM models m 
            JOIN providers p ON m.provider_id = p.id
            WHERE m.is_default = TRUE 
              AND p.is_active = TRUE
            LIMIT 1
        """)).mappings().first()
        if row:
            logger.debug("Default model ID retrieved: %s", row["id"])
            return row["id"]

        logger.warning("No default model found with an active provider; falling back to first active model.")
        row = session.execute(text("""
            SELECT m.id FROM models m
            JOIN providers p ON m.provider_id = p.id 
            WHERE p.is_active = TRUE
            LIMIT 1
        """)).mappings().first()
        if row:
            logger.debug("Using model ID %s as fallback", row["id"])
            return row["id"]

        logger.error("No models available with active providers.")
        return None

    @classmethod
    def create(cls, session: Session, chat_id: str, user_id: int, title: str = "New Chat", model_id: Optional[int] = None) -> "Chat":
        """
        Create a new chat record, using an existing Session.
        Accepts an optional model_id; uses the default if none is specified.
        Returns the created Chat instance.
        """
        cleaned_title = title.strip()[:50]
        if model_id is None:
            model_id = cls.get_default_model_id(session)
            if model_id is None:
                raise ValueError("No default model available and no model_id provided.")

        chat = cls(
            id=chat_id,
            user_id=user_id,
            title=cleaned_title,
            model_id=model_id,
            is_deleted=False
        )
        session.add(chat)
        session.commit()
        logger.info("Chat created: %s for user %s with model %s", chat_id, user_id, model_id)
        return chat

    @classmethod
    def soft_delete(cls, session: Session, chat_id: str) -> None:
        """
        Mark a chat as deleted (is_deleted=TRUE) without removing the record.
        """
        stmt = text("""
            UPDATE chats
            SET is_deleted = TRUE
            WHERE id = :chat_id
        """)
        session.execute(stmt, {"chat_id": chat_id})
        session.commit()
        logger.info("Chat soft-deleted: %s", chat_id)

    @classmethod
    def get_model(cls, session: Session, chat_id: str) -> Optional["Model"]:
        """
        Retrieve the associated Model for a given chat, using this Chat's model_id via ORM.
        """
        # Local import avoids circular references at module level
        from .model import Model

        chat = session.query(cls).filter(cls.id == chat_id).first()
        if chat and chat.model:
            # Example placeholder logic for an o1-type model
            if chat.model.model_type == 'o1':
                chat.model.api_version = '2025-01-01-preview'
                chat.model.temperature = 1.0
                chat.model.max_completion_tokens = 100000
            return chat.model
        # If no chat or model is set, fallback to the global default model
        return Model.get_default(session)

    @classmethod
    def add_message(
        cls,
        session: Session,
        chat_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Insert a new message row for the given chat, returning the inserted row's primary key.
        """
        logger.debug(
            "Adding message to chat %s - Role: %s, content length: %d",
            chat_id, role, len(content)
        )
        stmt = text("""
            INSERT INTO messages (chat_id, role, content, metadata, timestamp)
            VALUES (:chat_id, :role, :content, :metadata, NOW())
            RETURNING id
        """)
        result = session.execute(stmt, {
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "metadata": json.dumps(metadata, default=str) if metadata else '{}'
        })
        inserted_id = result.scalar()
        if inserted_id is None:
            raise ValueError("No message ID returned from insert.")
        session.commit()
        logger.debug("Added message to chat %s with message_id %s", chat_id, inserted_id)
        return int(inserted_id)

    @classmethod
    def get_messages(
        cls,
        session: Session,
        chat_id: str,
        include_system: bool = False
    ) -> List[Dict[str, Union[int, str, Dict[str, Any]]]]:
        """
        Retrieve messages for a particular chat from the 'messages' table.
        Optionally exclude system messages by default.
        """
        conditions = ["chat_id = :chat_id"]
        if not include_system:
            conditions.append("role != 'system'")

        stmt = text(f"""
            SELECT id, role, content, metadata, timestamp
            FROM messages
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp ASC
        """)
        rows = session.execute(stmt, {"chat_id": chat_id}).mappings().all()

        messages = []
        for row in rows:
            msg = dict(row)
            # Convert metadata from JSON if it's still a string
            if isinstance(msg['metadata'], str) and msg['metadata'].strip():
                try:
                    msg['metadata'] = json.loads(msg['metadata'])
                except Exception:
                    msg['metadata'] = {}
            messages.append(msg)
        return messages
