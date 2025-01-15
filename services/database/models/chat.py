from sqlalchemy import Column, Integer, String, JSON
from .base import Base, row_to_dict
from typing import Dict, List, Any, Optional
from services.database import db_session


class Chat(Base):
    """Chat model for storing messages and metadata."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    metadata = Column(JSON, nullable=True)

    @staticmethod
    def get_messages(chat_id: str, include_system: bool = False) -> List[Dict[str, Any]]:
        """Get all messages for a chat session."""
        with db_session() as session:
            query = session.query(Chat).filter(Chat.chat_id == chat_id)
            if not include_system:
                query = query.filter(Chat.role != "system")
            messages = query.order_by(Chat.id.asc()).all()
            return [row_to_dict(msg) for msg in messages]

    @staticmethod
    def add_message(chat_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a new message to the chat session."""
        with db_session() as session:
            message = Chat(
                chat_id=chat_id,
                role=role,
                content=content,
                metadata=metadata
            )
            session.add(message)
            session.commit()