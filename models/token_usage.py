from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import ForeignKey, JSON, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from models.base import Base
import logging

logger = logging.getLogger(__name__)

class TokenUsage(Base):
    """Tracks token usage per user/chat."""
    __tablename__ = "token_usage"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    chat_id: Mapped[str] = mapped_column(String)
    tokens_used: Mapped[int] = mapped_column(Integer)
    tokens_limit: Mapped[int] = mapped_column(Integer)
    last_updated: Mapped[datetime] = mapped_column(DateTime)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    @staticmethod
    def create(session: Session, user_id: int, chat_id: str, tokens_used: int) -> "TokenUsage":
        """Create a new token usage record."""
        try:
            new_usage = TokenUsage(
                user_id=user_id,
                chat_id=chat_id,
                tokens_used=tokens_used,
                last_updated=func.now(),
                metadata={"source": "file_upload"}
            )
            session.add(new_usage)
            session.commit()
            session.refresh(new_usage)
            return new_usage

            except Exception as e:
                session.rollback()
                logger.error(f"Failed to create token usage record: {e}")
                raise

    @staticmethod
    def within_rate_limit(session: Session, user_id: int, minutes_window: int = 60, token_limit: int = 10000) -> bool:
        """Check if a user is within token limit using provided session."""
        from datetime import datetime, timedelta
        from sqlalchemy import text

        cutoff = datetime.utcnow() - timedelta(minutes=minutes_window)

        row = session.execute(text("""
            SELECT COALESCE(SUM(tokens_used), 0) AS tokens_in_window
            FROM token_usage
            WHERE user_id = :user_id
              AND last_updated >= :cutoff
        """), {"user_id": user_id, "cutoff": cutoff}).mappings().first()

        if not row:
            return True

        tokens_in_window = int(row["tokens_in_window"])
        return tokens_in_window < token_limit

    @staticmethod
    def get_usage(user_id: int, chat_id: Optional[str] = None) -> Dict[str, int]:
        """Get token usage for a user/chat."""
        with db_session() as db:
            try:
                params = {"user_id": user_id}
                query = """
                    SELECT COALESCE(SUM(tokens_used), 0) as total_used,
                           COALESCE(MAX(tokens_limit), 100000) as token_limit
                    FROM token_usage 
                    WHERE user_id = :user_id
                """
                
                if chat_id:
                    query += " AND chat_id = :chat_id"
                    params["chat_id"] = chat_id

                result = db.execute(text(query), params).mappings().first()
                if not result:
                    return {
                        "used": 0,
                        "limit": 100000,
                        "remaining": 100000
                    }
                
                total_used = int(result["total_used"])
                token_limit = int(result["token_limit"])
                
                return {
                    "used": total_used,
                    "limit": token_limit,
                    "remaining": token_limit - total_used
                }

            except Exception as e:
                logger.error(f"Failed to get token usage: {e}")
                raise

    @staticmethod
    def update_usage(user_id: int, chat_id: str, additional_tokens: int) -> bool:
        """Update token usage and check limits."""
        with db_session() as db:
            try:
                # Get current usage
                current = TokenUsage.get_usage(user_id, chat_id)
                
                # Check if update would exceed limit
                if current["used"] + additional_tokens > current["limit"]:
                    return False
                    
                # Update usage
                query = text("""
                    INSERT INTO token_usage (
                        user_id, chat_id, tokens_used, tokens_limit,
                        last_updated, metadata
                    ) VALUES (
                        :user_id, :chat_id, :tokens_used, :token_limit,
                        CURRENT_TIMESTAMP, :metadata
                    )
                """)
                
                db.execute(query, {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "tokens_used": additional_tokens,
                    "token_limit": current["limit"],
                    "metadata": {"source": "update"}
                })
                
                db.commit()
                return True

            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update token usage: {e}")
                raise
