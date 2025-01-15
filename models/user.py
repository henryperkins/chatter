import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import text
from flask_login import UserMixin

from database import db_session, get_db_pool
from .base import row_to_dict

logger = logging.getLogger(__name__)


@dataclass
class User(UserMixin):
    """
    Represents a user in the system.
    """

    id: int
    username: str
    email: str
    password_hash: Optional[str] = None
    role: str = "user"  # 'user' or 'admin'
    created_at: datetime = datetime.now()
    reset_token: Optional[str] = None
    reset_token_expiry: Optional[datetime] = None
    is_active: bool = True

    def __post_init__(self):
        """Validate or adjust fields after dataclass initialization."""
        if self.id is not None:
            self.id = int(self.id)
        # Ensure password_hash is set to empty string if None
        if self.password_hash is None:
            self.password_hash = ""

    @staticmethod
    def get_by_id(user_id: int) -> Optional["User"]:
        """
        Retrieve a user by their ID.
        """
        with db_session() as db:
            try:
                query = text("SELECT * FROM users WHERE id = :user_id")
                row = db.execute(query, {"user_id": user_id}).fetchone()
                if row:
                    user_dict = row_to_dict(
                        row,
                        [
                            "id",
                            "username",
                            "email",
                            "password_hash",
                            "role",
                            "created_at",
                            "reset_token",
                            "reset_token_expiry",
                        ],
                    )
                    logger.debug(f"User retrieved by ID {user_id}: {user_dict}")
                    return User(**user_dict)
                logger.info(f"No user found with ID: {user_id}")
                return None
            except Exception as e:
                logger.error(f"Error retrieving user by ID {user_id}: {e}")
                raise

    @staticmethod
    def get_by_email(email: str) -> Optional["User"]:
        """
        Retrieve a user by their email address.
        """
        with db_session() as db:
            try:
                query = text("SELECT * FROM users WHERE email = :email")
                row = db.execute(query, {"email": email}).fetchone()
                if row:
                    user_dict = row_to_dict(
                        row,
                        [
                            "id",
                            "username",
                            "email",
                            "password_hash",
                            "role",
                            "created_at",
                            "reset_token",
                            "reset_token_expiry",
                        ],
                    )
                    logger.debug(f"User retrieved by email {email}: {user_dict}")
                    return User(**user_dict)
                logger.info(f"No user found with email: {email}")
                return None
            except Exception as e:
                logger.error(f"Error retrieving user by email {email}: {e}")
                raise

    @staticmethod
    def create(data: Dict[str, Any]) -> Optional[int]:
        """
        Create a new user record in the database.
        """
        with db_session() as db:
            try:
                query = text(
                    """
                    INSERT INTO users (
                        username, email, password_hash, role
                    ) VALUES (
                        :username, :email, :password_hash, :role
                    )
                    RETURNING id
                """
                )
                result = db.execute(query, data)
                user_id = result.scalar()

                if user_id is None:
                    logger.error("Failed to create user - no ID returned")
                    return None

                logger.info(f"User created with ID: {user_id}")
                return user_id
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create user: {e}")
                raise

    @staticmethod
    def update(user_id: int, data: Dict[str, Any]) -> None:
        """
        Update an existing user's attributes.
        """
        with db_session() as db:
            try:
                allowed_fields = {"username", "email", "password_hash", "role"}
                update_data = {
                    key: value for key, value in data.items() if key in allowed_fields
                }

                if not update_data:
                    logger.info(f"No valid fields to update for user ID {user_id}")
                    return

                set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
                params = {**update_data, "user_id": user_id}

                query = text(
                    f"""
                    UPDATE users
                    SET {set_clause}
                    WHERE id = :user_id
                """
                )

                db.execute(query, params)
                db.commit()
                logger.info(f"User updated (ID {user_id})")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update user {user_id}: {e}")
                raise
