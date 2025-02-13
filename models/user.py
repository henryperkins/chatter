from typing import Dict, Any, Optional, TypeVar, List
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy import text
import logging
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from database import db_session

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="User")


@dataclass
class User(UserMixin):
    """Represents a user in the system using raw SQL queries."""

    id: int
    username: str
    email: str
    password_hash: Optional[str] = None
    role: str = "user"
    created_at: datetime = field(default_factory=datetime.now)
    # Renamed to clarify we store hashed tokens:
    reset_token_hash: Optional[str] = None
    reset_token_expiry: Optional[datetime] = None
    _active: bool = field(default=True)
    otp_secret: Optional[str] = field(default=None)
    otp_required: bool = field(default=False)

    def __post_init__(self):
        """Dataclass hook for post-initialization."""
        pass

    def get_id(self) -> str:
        """Required by Flask-Login"""
        return str(self.id)

    @property
    def is_authenticated(self) -> bool:
        """User is considered authenticated if loaded from the DB."""
        return True

    @property
    def is_active(self) -> bool:
        """Check if user account is active."""
        return self._active

    @property
    def is_anonymous(self) -> bool:
        """By default, a real user is never anonymous."""
        return False

    def check_password(self, password: str) -> bool:
        """Check password with hash validation and error handling."""
        try:
            if not self.password_hash or not password:
                logger.debug("Missing password hash or empty password.")
                return False

            stored_hash = (
                self.password_hash.decode("utf-8")
                if isinstance(self.password_hash, bytes)
                else self.password_hash
            )
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

        # Parse created_at with better error handling
        created_at = None
        if "created_at" in data:
            try:
                if isinstance(data["created_at"], datetime):
                    created_at = data["created_at"]
                elif isinstance(data["created_at"], str):
                    # Handle PostgreSQL timestamp string
                    timestamp_str = str(data["created_at"])
                    if "+" in timestamp_str:  # Has timezone
                        created_at = datetime.fromisoformat(timestamp_str)
                    else:  # No timezone
                        created_at = datetime.fromisoformat(timestamp_str.replace(" ", "T"))
                    logger.debug(f"Parsed created_at from string: {created_at}")
                else:
                    logger.warning(f"Unexpected created_at type: {type(data['created_at'])}")
                    created_at = datetime.now()
            except Exception as e:
                logger.error(f"Error parsing created_at '{data.get('created_at')}': {e}")
                created_at = datetime.now()
        else:
            logger.warning("No created_at provided, using current time")
            created_at = datetime.now()

        # Parse reset_token_expiry if present
        reset_token_expiry = None
        if data.get("reset_token_expiry"):
            try:
                if isinstance(data["reset_token_expiry"], datetime):
                    reset_token_expiry = data["reset_token_expiry"]
                else:
                    reset_token_expiry = datetime.fromisoformat(str(data["reset_token_expiry"]))
            except Exception as e:
                logger.error(f"Error parsing reset_token_expiry: {e}")
                reset_token_expiry = None

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
        )

    @classmethod
    def get(cls, user_id: int) -> Optional["User"]:
        """Get user by ID for Flask-Login."""
        return cls.get_by_id(user_id)

    @staticmethod
    def get_by_id(user_id: int) -> Optional["User"]:
        """Retrieve a user by their ID with proper transaction isolation."""
        if not user_id:
            logger.debug("get_by_id called with null/zero user_id")
            return None

        try:
            with db_session() as db:
                result = db.execute(
                    text(
                        """
                        SELECT id, username, email, password_hash, role,
                               created_at, reset_token_hash, reset_token_expiry, is_active
                        FROM users
                        WHERE id = :user_id
                        """
                    ),
                    {"user_id": user_id},
                ).mappings().first()

                if not result:
                    logger.warning(f"No user found in database with ID: {user_id}")
                    return None

                user = User.from_dict(dict(result))
                
                if not user.is_active:
                    logger.debug(f"Retrieved inactive user with ID: {user_id}")
                else:
                    logger.debug(f"Retrieved active user with ID: {user_id}")
                    
                return user

        except Exception as e:
            logger.error(f"Database error retrieving user {user_id}: {str(e)}", exc_info=True)
            return None

    @classmethod
    def get_by_email(cls, email: str) -> Optional["User"]:
        """Get user by email using a managed database session."""
        try:
            with db_session() as db:
                row = db.execute(
                    text(
                        """
                        SELECT id, username, email, password_hash, role,
                               created_at, reset_token_hash, reset_token_expiry, is_active
                        FROM users
                        WHERE LOWER(email) = LOWER(:email)
                          AND is_active = TRUE
                        """
                    ),
                    {"email": email},
                ).mappings().first()

                if not row:
                    logger.info(f"No user found with email: {email}")
                    return None

                return cls.from_dict(dict(row))

        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving user by email {email}: {str(e)}")
            return None

    @staticmethod
    def create(username: str, email: str, password: str) -> "User":
        """Create a new user with proper transaction handling."""
        try:
            password_hash = generate_password_hash(password)
            if isinstance(password_hash, bytes):
                password_hash = password_hash.decode("utf-8")

            with db_session() as db:
                # First ensure we have a default model
                default_model = db.execute(
                    text("SELECT id FROM models WHERE is_default = TRUE")
                ).scalar()
                
                if not default_model:
                    # Create default model if none exists
                    from database import create_default_model
                    create_default_model(db)
                    db.commit()  # Commit the model creation first
                
                # Check if this is the first user
                user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
                is_first_user = user_count == 0

                # Now check for existing users
                existing = db.execute(
                    text("""
                        SELECT 1 FROM users
                        WHERE LOWER(username) = LOWER(:username)
                        OR LOWER(email) = LOWER(:email)
                    """),
                    {
                        "username": username.strip(),
                        "email": email.strip().lower()
                    }
                ).first()

                if existing:
                    raise ValueError("Username or email already exists")

                # Insert new user - first user gets admin role
                result = db.execute(
                    text(
                        """
                        INSERT INTO users (
                            username, email, password_hash, role,
                            reset_token_hash, reset_token_expiry,
                            created_at, is_active
                        )
                        VALUES (
                            :username, :email, :password_hash, :role,
                            NULL, NULL, NOW(), TRUE
                        )
                        RETURNING id, created_at
                        """
                    ),
                    {
                        "username": username.strip(),
                        "email": email.strip().lower(),
                        "password_hash": password_hash,
                        "role": "admin" if is_first_user else "user"
                    },
                ).mappings().first()

                if not result:
                    logger.error("User creation failed - no result returned")
                    raise ValueError("Failed to create user")
                    
                user_id = result["id"]
                logger.debug(f"User created with ID {user_id} and created_at {result.get('created_at')}")
                db.commit()
                
                created_user = User.get_by_id(user_id)
                if not created_user:
                    logger.error(f"Failed to retrieve created user with ID {user_id}")
                    raise ValueError("Failed to create user")
                
                logger.debug(f"Successfully created and retrieved user: {created_user.to_dict()}")
                return created_user

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
    def verify_user_exists(user_id: int) -> bool:
        """Verify that a user exists and is active."""
        try:
            with db_session() as db:
                exists = db.execute(
                    text(
                        """
                        SELECT 1 FROM users
                        WHERE id = :user_id
                          AND is_active = TRUE
                        """
                    ),
                    {"user_id": user_id},
                ).scalar() is not None
                logger.debug(
                    f"User existence check for ID {user_id}: {'Exists' if exists else 'Not found'}"
                )
                return exists
        except Exception as e:
            logger.error(f"Error verifying user existence for ID {user_id}: {str(e)}")
            return False

    @classmethod
    def get_by_username(cls, username: str) -> Optional["User"]:
        """Retrieve a user by username (case-insensitive)."""
        try:
            with db_session() as db:
                row = db.execute(
                    text(
                        """
                        SELECT id, username, email, password_hash, role,
                               created_at, reset_token_hash, reset_token_expiry, is_active
                        FROM users
                        WHERE LOWER(username) = LOWER(:username)
                          AND is_active = TRUE
                        """
                    ),
                    {"username": username.strip()},
                ).mappings().first()

                if not row:
                    logger.debug(f"No user found for username: {username}")
                    return None

                return cls.from_dict(dict(row))
        except Exception as e:
            logger.error(f"Error retrieving user by username {username}: {str(e)}")
            return None

    @staticmethod
    def update(user_id: int, data: Dict[str, Any]) -> bool:
        """Update an existing user's attributes."""
        try:
            with db_session() as db:
                allowed_fields = {"username", "email", "password_hash", "role", "is_active"}
                update_data = {k: v for k, v in data.items() if k in allowed_fields}

                if not update_data:
                    logger.info(f"No valid fields to update for user ID {user_id}")
                    return False

                set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
                params = {**update_data, "user_id": user_id}

                result = db.execute(
                    text(
                        f"""
                        UPDATE users
                        SET {set_clause}
                        WHERE id = :user_id
                        RETURNING id
                        """
                    ),
                    params,
                )

                success = result.scalar() is not None
                if success:
                    logger.info(f"User {user_id} updated successfully")
                return success

        except SQLAlchemyError as e:
            logger.error(f"Database error updating user {user_id}: {e}")
            raise ValueError(f"Failed to update user: {str(e)}")

    @staticmethod
    def deactivate(user_id: int) -> bool:
        """Deactivate a user account."""
        try:
            with db_session() as db:
                result = db.execute(
                    text(
                        """
                        UPDATE users
                        SET is_active = FALSE
                        WHERE id = :user_id
                        RETURNING id
                        """
                    ),
                    {"user_id": user_id},
                )
                success = result.scalar() is not None
                if success:
                    logger.info(f"User {user_id} deactivated")
                return success
        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {e}")
            return False

    @staticmethod
    def validate_reset_token(token: str) -> Optional["User"]:
        """Validate a password reset token by comparing hashes."""
        try:
            with db_session() as db:
                # Get all users with unexpired reset tokens
                results = db.execute(
                    text(
                        """
                        SELECT id, username, email, password_hash, role,
                               created_at, reset_token_hash, reset_token_expiry, is_active
                        FROM users
                        WHERE reset_token_expiry > NOW()
                          AND is_active = TRUE
                        """
                    )
                ).mappings().all()

                # Compare hashes in Python
                for user_data in results:
                    if check_password_hash(user_data["reset_token_hash"], token):
                        return User.from_dict(dict(user_data))
                return None
        except Exception as e:
            logger.error(f"Error validating reset token: {e}")
            return None

    @staticmethod
    def set_role(user_id: int, role: str) -> bool:
        """Change a user's role."""
        try:
            with db_session() as db:
                result = db.execute(
                    text(
                        """
                        UPDATE users
                        SET role = :role
                        WHERE id = :user_id
                        RETURNING id
                        """
                    ),
                    {"user_id": user_id, "role": role},
                )
                success = result.scalar() is not None
                if success:
                    logger.info(f"User {user_id} role updated to {role}")
                return success
        except Exception as e:
            logger.error(f"Error updating role for user {user_id}: {e}")
            return False

    def change_password(self, new_password: str) -> bool:
        """Change user's password and clear any reset token data."""
        try:
            password_hash = generate_password_hash(new_password)
            if isinstance(password_hash, bytes):
                password_hash = password_hash.decode("utf-8")

            with db_session() as db:
                result = db.execute(
                    text(
                        """
                        UPDATE users
                        SET password_hash = :password_hash,
                            reset_token_hash = NULL,
                            reset_token_expiry = NULL
                        WHERE id = :user_id
                        RETURNING id
                        """
                    ),
                    {"password_hash": password_hash, "user_id": self.id},
                )
                success = result.scalar() is not None
                if success:
                    db.commit()
                    self.password_hash = password_hash
                    logger.info(f"Password changed for user {self.id}")
                return success
        except Exception as e:
            logger.error(f"Error changing password for user {self.id}: {e}")
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
    def list_active_users(cls) -> List["User"]:
        """Get all active users."""
        try:
            with db_session() as db:
                results = db.execute(
                    text(
                        """
                        SELECT id, username, email, password_hash, role,
                               created_at, is_active
                        FROM users
                        WHERE is_active = TRUE
                        ORDER BY created_at DESC
                        """
                    )
                ).mappings().all()

                return [cls.from_dict(dict(row)) for row in results]
        except Exception as e:
            logger.error(f"Error listing active users: {e}")
            return []

    @staticmethod
    def bulk_deactivate(user_ids: List[int]) -> bool:
        """Deactivate multiple users at once."""
        try:
            with db_session() as db:
                result = db.execute(
                    text(
                        """
                        UPDATE users
                        SET is_active = FALSE
                        WHERE id = ANY(:user_ids)
                        RETURNING id
                        """
                    ),
                    {"user_ids": user_ids},
                )
                affected = result.rowcount
                logger.info(f"Deactivated {affected} users")
                return affected > 0
        except Exception as e:
            logger.error(f"Error bulk deactivating users: {e}")
            return False
