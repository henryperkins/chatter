import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from flask_login import UserMixin

from database import db_session
from .base import row_to_dict

logger = logging.getLogger(__name__)


@dataclass
class User(UserMixin):
    """Represents a user in the system."""
    id: int
    username: str
    email: str
    password_hash: Optional[str] = None
    role: str = "user"
    created_at: datetime = field(default_factory=datetime.now)
    reset_token: Optional[str] = None
    reset_token_expiry: Optional[datetime] = None
    is_active: bool = True

    @staticmethod
    def from_dict(data: dict) -> "User":
        """Create User instance from dictionary"""
        if not all(k in data for k in ["id", "username", "email"]):
            raise ValueError("Missing required fields in user data")
            
        return User(
            id=int(data["id"]),
            username=data["username"],
            email=data["email"],
            password_hash=data.get("password_hash"),
            role=data.get("role", "user"),
            created_at=data.get("created_at", datetime.now()),
            reset_token=data.get("reset_token"),
            reset_token_expiry=data.get("reset_token_expiry"),
            is_active=data.get("is_active", True)
        )

    @classmethod
    def get(cls, user_id: int) -> Optional["User"]:
        """Get user by ID for Flask-Login"""
        return cls.get_by_id(user_id)

    @staticmethod
    def get_by_id(user_id: int) -> Optional["User"]:
        """Retrieve a user by their ID with proper session handling"""
        try:
            with db_session() as db:
                query = text("SELECT * FROM users WHERE id = :user_id")
                result = db.execute(query, {"user_id": user_id})
                row = result.mappings().first()
                
                if not row:
                    logger.info(f"No user found with ID: {user_id}")
                    return None
                    
                # Convert row to dictionary
                user_data = dict(row)
                
                # Create User instance
                return User.from_dict(user_data)
                
        except Exception as e:
            logger.error(f"Error retrieving user by ID {user_id}: {e}")
            return None

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
            except IntegrityError as e:
                db.rollback()
                logger.error(f"Failed to create user due to integrity error: {e}")
                raise ValueError("User with this email or username already exists.")
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
