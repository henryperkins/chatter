from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Union
from sqlalchemy import text
from database import db_session
import logging

logger = logging.getLogger(__name__)

@dataclass
class TokenUsage:
    """Tracks token usage per user/chat."""
    
    id: int
    user_id: int
    chat_id: str
    tokens_used: int
    tokens_limit: int
    last_updated: datetime
    metadata: Optional[Dict[str, Any]] = None

    @staticmethod
    def create(user_id: int, chat_id: str, tokens_used: int) -> "TokenUsage":
        """Create a new token usage record."""
        with db_session() as db:
            try:
                # Get user's token limit from their role/settings
                limit_query = text("""
                    SELECT COALESCE(
                        (SELECT token_limit FROM user_settings WHERE user_id = :user_id),
                        100000  -- Default limit
                    ) as token_limit
                """)
                token_limit = int(db.execute(limit_query, {"user_id": user_id}).scalar() or 100000)

                query = text("""
                    INSERT INTO token_usage (
                        user_id, chat_id, tokens_used, tokens_limit,
                        last_updated, metadata
                    ) VALUES (
                        :user_id, :chat_id, :tokens_used, :token_limit,
                        CURRENT_TIMESTAMP, :metadata
                    ) RETURNING id, last_updated
                """)
                
                result = db.execute(query, {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "tokens_used": tokens_used,
                    "token_limit": token_limit,
                    "metadata": {"source": "file_upload"}
                })
                
                result = result.mappings().first()
                if not result:
                    raise ValueError("Failed to create token usage record")
                
                db.commit()
                
                return TokenUsage(
                    id=result["id"],
                    user_id=user_id,
                    chat_id=chat_id,
                    tokens_used=tokens_used,
                    tokens_limit=token_limit,
                    last_updated=result["last_updated"],
                    metadata={"source": "file_upload"}
                )

            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create token usage record: {e}")
                raise

    @staticmethod
    def within_rate_limit(user_id: int, minutes_window: int = 60, token_limit: int = 10000) -> bool:
        """
        Check if a user is within the specified token limit for a given time window.
        Defaults to 10,000 tokens per 60 minutes.
        """
        from datetime import datetime, timedelta
        from database import db_session
        from sqlalchemy import text

        cutoff = datetime.utcnow() - timedelta(minutes=minutes_window)

        with db_session() as db:
            row = db.execute(text("""
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
