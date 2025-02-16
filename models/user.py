from typing import Dict, Any, Optional, TypeVar, List, Literal, Self
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, func, or_, update
import logging
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy.orm import Session, Mapped, mapped_column
from models.base import Base
from models.model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="User")


class User(Base, UserMixin):
    """Represents a user in the system using raw SQL queries."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Renamed to clarify we store hashed tokens:
    reset_token_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    _active: Mapped[bool] = mapped_column(Boolean, default=True)
    otp_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    otp_required: Mapped[bool] = mapped_column(Boolean, default=False)
    account_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)

    def __post_init__(self):
        """Dataclass hook for post-initialization."""
        pass

    def get_id(self) -> str:
        """Required by Flask-Login"""
        return str(self.id)

    @property
    def is_authenticated(self) -> Literal[True]:
        """User is considered authenticated if loaded from the DB."""
        return True

    @property
    def is_active(self) -> Literal[True]:
        """Check if user account is active."""
        if not self._active:
            raise ValueError("User is not active")
        return True

    @property
    def is_anonymous(self) -> Literal[False]:
        """By default, a real user is never anonymous."""
        return False

    def check_password(self, password: str) -> bool:
        """Check password with hash validation and error handling."""
        try:
            if not password:
                logger.debug("Empty password provided.")
                return False

            if not self.password_hash:
                logger.debug("User has no password hash set.")
                return False

            stored_hash = (
                self.password_hash.decode("utf-8")
                if isinstance(self.password_hash, bytes)
                else self.password_hash
            )
            if not stored_hash:
                logger.debug("Invalid password hash format.")
                return False

            # Use type guard to narrow type
            if not isinstance(stored_hash, str):
                logger.debug("Password hash is not a valid string")
                return False
            # No need to cast since isinstance already confirmed it's a string
            return check_password_hash(stored_hash, password)
        except Exception as e:
            logger.error(f"Password check failed for user {self.id}: {str(e)}")
            return False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """Create User instance from dictionary. Expects certain keys."""
        if not all(k in data for k in ["id", "username", "email"]):
            logger.error(f"Missing required fields in user data: {data.keys()}")
            raise ValueError("Missing required fields in user data")

        # Handle datetime fields
        created_at = data.get("created_at") or datetime.utcnow()
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        
        reset_token_expiry = data.get("reset_token_expiry")
        if isinstance(reset_token_expiry, str):
            reset_token_expiry = datetime.fromisoformat(reset_token_expiry.replace("Z", "+00:00"))

        return cls(
            id=int(data["id"]),
            username=data["username"],
            email=data["email"],
            password_hash=data.get("password_hash"),
            role=data.get("role", "user"),
            created_at=created_at,
            reset_token_hash=data.get("reset_token_hash"),
            reset_token_expiry=reset_token_expiry,
            _active=data.get("is_active", True),
            account_locked_until=data.get("account_locked_until"),
        )

        # Ensure code is indented under the 'with' block
=======
            return cls.get_by_id(session, int(user_id))
>>>>>>> d13c2ede36cc1ba63584bcfb67827f7dcf2c2ba6

    @classmethod
    def get_by_id(cls, session: Session, user_id: int) -> Optional["User"]:
        """Retrieve a user by their ID with proper transaction isolation."""
        if not user_id:
            logger.debug("get_by_id called with null/zero user_id")
            return None

        try:
            return session.query(cls).filter_by(id=user_id).first()
        except Exception as e:
            logger.error(f"Database error retrieving user {user_id}: {str(e)}", exc_info=True)
            return None

    @classmethod
    def get_by_email(cls, session: Session, email: str) -> Optional["User"]:
        """Get user by email using provided database session."""
        try:
            return session.query(cls).filter(
                func.lower(cls.email) == func.lower(email),
                cls._active.is_(True)
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving user by email {email}: {str(e)}")
            return None

    @classmethod
    def create(cls, session: Session, username: str, email: str, password: str) -> "User":
        """Create a new user with provided database session."""
        try:
            # First ensure we have a default model
            default_model = session.query(Model).filter_by(is_default=True).first()
            if not default_model:
                # Create default model if none exists
                from database import create_default_model
                create_default_model(session)
                session.commit()  # Commit the model creation first
            
            # Check if this is the first user
            is_first_user = session.query(cls).count() == 0

            # Check for existing users
            existing = session.query(cls).filter(
                or_(
                    func.lower(cls.username) == func.lower(username.strip()),
                    func.lower(cls.email) == func.lower(email.strip())
                )
            ).first()

            if existing:
                raise ValueError("Username or email already exists")

            # Create password hash
            password_hash = generate_password_hash(password)
            if isinstance(password_hash, bytes):
                password_hash = password_hash.decode("utf-8")

            # Create new user
            new_user = cls(
                username=username.strip(),
                email=email.strip().lower(),
                password_hash=password_hash,
                role="admin" if is_first_user else "user",
                _active=True
            )
            session.add(new_user)
            session.flush()  # Get the ID without committing
            
            logger.debug(f"User created with ID {new_user.id}")
            session.commit()
            
            logger.debug(f"Successfully created and retrieved user: {new_user.to_dict()}")
            return new_user
>>>>>>> d13c2ede36cc1ba63584bcfb67827f7dcf2c2ba6
=======
            # Create new user
            new_user = cls(
                username=username.strip(),
                email=email.strip().lower(),
                password_hash=password_hash,
                role="admin" if is_first_user else "user",
                _active=True
            )
            session.add(new_user)
            session.flush()  # Get the ID without committing
            
            logger.debug(f"User created with ID {new_user.id}")
            session.commit()
            
            logger.debug(f"Successfully created and retrieved user: {new_user.to_dict()}")
            return new_user
>>>>>>> d13c2ede36cc1ba63584bcfb67827f7dcf2c2ba6

        except IntegrityError as e:
            logger.error(
                f"Integrity error creating user '{username}': {e}",
                exc_info=True,
                extra={
                    "file": "models/user.py",
                    "phase": "user creation",
                    "username": username,
                    "email": email
                }
            )
            raise ValueError("Username or email already exists")
        except Exception as e:
            logger.error(
                f"Error creating user '{username}': {e}",
                exc_info=True,
                extra={
                    "file": "models/user.py",
                    "phase": "user creation",
                    "username": username,
                    "email": email
                }
            )
            raise

    @staticmethod
    def verify_user_exists(session: Session, user_id: int) -> bool:
        """Verify that a user exists and is active using provided session."""
        try:
            exists = session.query(User).filter(
                User.id == user_id,
                User._active.is_(True)
            ).first() is not None
            logger.debug(
                f"User existence check for ID {user_id}: {'Exists' if exists else 'Not found'}"
            )
            return exists
        except Exception as e:
            logger.error(f"Error verifying user existence for ID {user_id}: {str(e)}")
            return False

    @classmethod
    def get_by_username(cls, session: Session, username: str) -> Optional["User"]:
        """Retrieve a user by username (case-insensitive)."""
        try:
            return session.query(cls).filter(
                func.lower(cls.username) == func.lower(username.strip()),
                cls._active.is_(True)
            ).first()
        except Exception as e:
            logger.error(f"Error retrieving user by username {username}: {str(e)}")
            return None

    @staticmethod
    def update(session: Session, user_id: int, data: Dict[str, Any]) -> bool:
        """Update an existing user's attributes using provided session."""
        try:
            allowed_fields = {"username", "email", "password_hash", "role", "_active"}
            update_data = {k: v for k, v in data.items() if k in allowed_fields}

            if not update_data:
                logger.info(f"No valid fields to update for user ID {user_id}")
                return False

            # Convert is_active to _active for database field
            if "is_active" in update_data:
                update_data["_active"] = update_data.pop("is_active")

            # Use SQLAlchemy update
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(**update_data)
                .returning(User.id)
            )
            result = session.execute(stmt)
            success = result.scalar() is not None

            if success:
                logger.info(f"User {user_id} updated successfully")
                session.commit()
            return success

        except SQLAlchemyError as e:
            logger.error(f"Database error updating user {user_id}: {e}")
            session.rollback()
            raise ValueError(f"Failed to update user: {str(e)}")

    @staticmethod
    def deactivate(session: Session, user_id: int) -> bool:
        """Deactivate a user account using provided session."""
        try:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(_active=False)
                .returning(User.id)
            )
            result = session.execute(stmt)
            success = result.scalar() is not None
            
            if success:
                logger.info(f"User {user_id} deactivated")
                session.commit()
            return success
        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {e}")
            session.rollback()
            return False

    @staticmethod
    def validate_reset_token(session: Session, token: str) -> Optional["User"]:
        """Validate a password reset token by comparing hashes using provided session."""
        try:
            # Get all users with unexpired reset tokens
            users = (
                session.query(User)
                .filter(
                    User.reset_token_expiry > func.now(),
                    User._active.is_(True)
                )
                .all()
            )

            # Compare hashes in Python
            for user in users:
                if user.reset_token_hash and isinstance(user.reset_token_hash, str):
                    if check_password_hash(user.reset_token_hash, token):
                        return user
            return None
        except Exception as e:
            logger.error(f"Error validating reset token: {e}")
            return None

    @staticmethod
    def set_role(session: Session, user_id: int, role: str) -> bool:
        """Change a user's role using provided session."""
        try:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(role=role)
                .returning(User.id)
            )
            result = session.execute(stmt)
            success = result.scalar() is not None
            
            if success:
                logger.info(f"User {user_id} role updated to {role}")
                session.commit()
            return success
        except Exception as e:
            logger.error(f"Error updating role for user {user_id}: {e}")
            session.rollback()
            return False

    def save(self, session: Session) -> bool:
        """Save current user state to database using provided session."""
        try:
            stmt = (
                update(User)
                .where(User.id == self.id)
                .values(
                    failed_login_attempts=self.failed_login_attempts,
                    account_locked_until=self.account_locked_until
                )
                .returning(User.id)
            )
            result = session.execute(stmt)
            success = result.scalar() is not None
            
            if success:
                logger.info(f"Updated user {self.id} state")
                session.commit()
            return success
        except Exception as e:
            logger.error(f"Error saving user {self.id} state: {e}")
            session.rollback()
            return False

    def change_password(self, session: Session, new_password: str) -> bool:
        """Change user's password and clear any reset token data using provided session."""
        try:
            password_hash = generate_password_hash(new_password)
            if isinstance(password_hash, bytes):
                password_hash = password_hash.decode("utf-8")

            stmt = (
                update(User)
                .where(User.id == self.id)
                .values(
                    password_hash=password_hash,
                    reset_token_hash=None,
                    reset_token_expiry=None
                )
                .returning(User.id)
            )
            result = session.execute(stmt)
            success = result.scalar() is not None
            
            if success:
                self.password_hash = password_hash
                logger.info(f"Password changed for user {self.id}")
                session.commit()
            return success
        except Exception as e:
            logger.error(f"Error changing password for user {self.id}: {e}")
            session.rollback()
            return False

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == "admin"

    def to_dict(self) -> Dict[str, Any]:
        """Convert user object to dictionary."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_active": self.is_active,
        }

    @classmethod
    def list_active_users(cls, session: Session) -> List[Self]:
        """Get all active users using provided session."""
        try:
            return (
                session.query(cls)
                .filter(cls._active.is_(True))
                .order_by(cls.created_at.desc())
                .all()
            )
        except Exception as e:
            logger.error(f"Error listing active users: {e}")
            return []

    @staticmethod
    def bulk_deactivate(session: Session, user_ids: List[int]) -> bool:
        """Deactivate multiple users at once using provided session."""
        try:
            stmt = (
                update(User)
                .where(User.id.in_(user_ids))
                .values(_active=False)
                .returning(User.id)
            )
            result = session.execute(stmt)
            affected = len(result.all())
            
            if affected > 0:
                logger.info(f"Deactivated {affected} users")
                session.commit()
            return affected > 0
        except Exception as e:
            logger.error(f"Error bulk deactivating users: {e}")
            session.rollback()
            return False
