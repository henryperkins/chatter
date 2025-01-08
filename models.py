"""
models.py

This module contains classes and methods for managing users, models,
chats, and files in the database.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Union, Any, Mapping, Dict

from database import get_db  # Use SQLAlchemy session manager
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class User:
    """
    Represents a user in the system.
    """

    id: int
    username: str
    email: str
    role: str = "user"

    @staticmethod
    def get_by_id(user_id: int) -> Optional["User"]:
        """
        Retrieve a user by ID from the database.
        """
        db: Session = get_db()
        user_row = db.execute(
            "SELECT * FROM users WHERE id = :user_id", {"user_id": user_id}
        ).fetchone()
        if user_row:
            return User(**dict(user_row))
        return None

    @property
    def is_authenticated(self) -> bool:
        """Indicates whether this user is authenticated."""
        return True

    @property
    def is_active(self) -> bool:
        """Indicates whether this user is active."""
        return True

    @property
    def is_anonymous(self) -> bool:
        """Indicates whether this user is anonymous."""
        return False

    def get_id(self) -> str:
        """Return the user ID as a string."""
        return str(self.id)


@dataclass
class Model:
    """
    Represents an AI model in the system.
    """

    id: int
    name: str
    deployment_name: str
    description: Optional[str]
    model_type: str
    api_endpoint: str
    api_key: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: int = 500
    is_default: bool = False
    requires_o1_handling: bool = False
    api_version: str = "2024-10-01-preview"
    version: int = 1
    created_at: Optional[str] = None

    def __post_init__(self):
        """
        Validate or adjust fields after dataclass initialization.
        """
        self.id = int(self.id)

    @staticmethod
    def get_default() -> Optional["Model"]:
        """
        Retrieve the default model (where `is_default=1`).
        """
        db: Session = get_db()
        row = db.execute(
            "SELECT * FROM models WHERE is_default = 1"
        ).fetchone()
        if row:
            return Model(**dict(row))
        return None

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.
        """
        db: Session = get_db()
        row = db.execute(
            "SELECT * FROM models WHERE id = :model_id", {"model_id": model_id}
        ).fetchone()
        if row:
            return Model(**dict(row))
        return None

    @staticmethod
    def get_all(limit: int = 10, offset: int = 0) -> List["Model"]:
        """
        Retrieve all models from the database, optionally paginated.
        """
        db: Session = get_db()
        rows = db.execute(
            "SELECT * FROM models ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
            {"limit": limit, "offset": offset}
        ).fetchall()
        return [Model(**dict(row)) for row in rows]

    @staticmethod
    def set_default(model_id: int):
        """
        Set a model as the default, and remove the default status from any other model.
        """
        db: Session = get_db()
        # Reset the current default model
        db.execute("UPDATE models SET is_default = 0 WHERE is_default = 1")

        # Set the new model as default
        db.execute(
            "UPDATE models SET is_default = 1 WHERE id = :model_id",
            {"model_id": model_id}
        )

        # Ensure only one default model exists
        duplicate_check = db.execute(
            "SELECT COUNT(*) as count FROM models WHERE is_default = 1"
        ).fetchone()
        if duplicate_check["count"] > 1:
            raise ValueError("More than one default model exists.")

        logger.info("Model set as default (ID %d)", model_id)

    @staticmethod
    def create(data: Dict[str, Any]) -> Optional[int]:
        """
        Create a new model record in the database.

        Args:
            data (dict): A dictionary containing model attributes.

        Returns:
            Optional[int]: The ID of the newly created model, or None if creation failed.

        Raises:
            ValueError: If required fields are missing or invalid
        """
        db: Session = get_db()
        # Handle temperature for o1-preview models
        if data.get("requires_o1_handling", False):
            data["temperature"] = None

        result = db.execute(
            """
            INSERT INTO models (
                name,
                deployment_name,
                description,
                api_endpoint,
                api_key,
                api_version,
                temperature,
                max_tokens,
                max_completion_tokens,
                model_type,
                requires_o1_handling,
                is_default,
                version
            ) VALUES (
                :name,
                :deployment_name,
                :description,
                :api_endpoint,
                :api_key,
                :api_version,
                :temperature,
                :max_tokens,
                :max_completion_tokens,
                :model_type,
                :requires_o1_handling,
                :is_default,
                :version
            )
            """,
            {
                "name": data["name"],
                "deployment_name": data["deployment_name"],
                "description": data.get("description", ""),
                "api_endpoint": data["api_endpoint"],
                "api_key": data["api_key"],
                "api_version": data["api_version"],
                "temperature": data.get("temperature"),
                "max_tokens": data.get("max_tokens"),
                "max_completion_tokens": data["max_completion_tokens"],
                "model_type": data["model_type"],
                "requires_o1_handling": data.get("requires_o1_handling", False),
                "is_default": data.get("is_default", False),
                "version": data.get("version", 1),
            }
        )
        model_id = result.lastrowid
        if model_id is None:
            logger.error("Failed to create model - no ID returned")
            return None

        # If the new model is set as default, unset default on other models
        if data.get("is_default", False):
            db.execute(
                "UPDATE models SET is_default = 0 WHERE id != :model_id",
                {"model_id": model_id}
            )

        logger.info("Model created with ID: %d", model_id)
        return model_id

    @staticmethod
    def update(model_id: int, data: Dict[str, Any]) -> None:
        try:
            db: Session = get_db()
            # 1. Validate the data (optional, but recommended)
            Model.validate_model_config(data)

            # 2. Fetch the existing model
            model = Model.get_by_id(model_id)
            if not model:
                raise ValueError(f"Model with ID {model_id} not found.")

            # 3. Update model attributes
            for key, value in data.items():
                setattr(model, key, value)

            # 4. Build the SQL UPDATE statement dynamically
            ALLOWED_FIELDS = {
                'name', 'deployment_name', 'description', 'api_endpoint',
                'api_key', 'api_version', 'temperature', 'max_tokens',
                'max_completion_tokens', 'model_type', 'requires_o1_handling',
                'is_default', 'version'
            }
            set_clause = ", ".join(f"{key} = :{key}" for key in data if key in ALLOWED_FIELDS)
            params = {**data, "model_id": model_id}

            # 5. Execute the update
            query = f"""
                UPDATE models
                SET {set_clause}
                WHERE id = :model_id
            """
            db.execute(query, params)
            db.commit()

            # 6. Handle default model logic (if applicable)
            if data.get("is_default"):
                db.execute(
                    "UPDATE models SET is_default = 0 WHERE id != :model_id",
                    {"model_id": model_id}
                )

            logger.info("Model updated (ID %d)", model_id)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update model {model_id}: {e}")
            raise

    @staticmethod
    def validate_model_config(config: Mapping[str, Any]) -> None:
        """
        Validate model configuration parameters.
        
        Args:
            config: Dictionary containing model configuration
            
        Raises:
            ValueError: If any parameters are invalid
        """
        required_fields = [
            "name",
            "deployment_name",
            "api_endpoint",
            "api_key",
            "api_version",
            "model_type",
            "max_completion_tokens",
        ]

        for field_name in required_fields:
            val = config.get(field_name)
            if not val:
                raise ValueError(f"Missing required field: {field_name}")

        # Validate API endpoint
        api_endpoint = config["api_endpoint"]
        if (
            not api_endpoint.startswith("https://")
            or "openai.azure.com" not in api_endpoint
        ):
            raise ValueError("Invalid Azure OpenAI API endpoint.")
        if not config.get("requires_o1_handling", False):
            temperature = config.get("temperature")
            if temperature is not None and not (0 <= float(temperature) <= 2):
                raise ValueError(
                    "Temperature must be between 0 and 2 or NULL for o1-preview models"
                )

        # Validate max_tokens
        max_tokens = config.get("max_tokens", None)
        if max_tokens is not None and (int(max_tokens) <= 0):
            raise ValueError("Max tokens must be a positive integer.")

        # Add validation for max_completion_tokens
        if config.get('max_completion_tokens'):
            if not (0 < config['max_completion_tokens'] <= 16384):
                raise ValueError("max_completion_tokens must be between 1 and 16384")

    @staticmethod
    def cleanup_orphaned_files() -> None:
        """Remove files without database references"""
        db: Session = get_db()
        # Implementation needed

    @staticmethod
    def get_user_chats(user_id: int, limit: int = 10, offset: int = 0):
        """
        Fetch user chats with model information to avoid N+1 query problem.
        
        Args:
            user_id: ID of the user
            limit: Number of records to fetch
            offset: Number of records to skip
        
        Returns:
            List of user chats with model information
        """
        query = """
        SELECT c.*, m.name as model_name 
        FROM chats c 
        LEFT JOIN models m ON c.model_id = m.id 
        WHERE c.user_id = :user_id 
        ORDER BY c.created_at DESC 
        LIMIT :limit OFFSET :offset
        """
        db: Session = get_db()
        return db.execute(query, {"user_id": user_id, "limit": limit, "offset": offset}).fetchall()


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
        db: Session = get_db()
        logger.debug("Checking ownership for chat_id: %s, user_id: %d", chat_id, user_id)
        chat = db.execute(
            "SELECT id FROM chats WHERE id = :chat_id AND user_id = :user_id",
            {"chat_id": chat_id, "user_id": user_id}
        ).fetchone()
        logger.debug("Query result for chat_id %s: %s", chat_id, chat)
        return chat is not None

    @staticmethod
    def is_title_default(chat_id: str) -> bool:
        """
        Check whether a chat has the default title.
        """
        db: Session = get_db()
        row = db.execute(
            "SELECT title FROM chats WHERE id = :chat_id", {"chat_id": chat_id}
        ).fetchone()
        return bool(row) and row["title"] == "New Chat"

    @staticmethod
    def update_title(chat_id: str, new_title: str) -> None:
        """
        Update the title of a chat with validation.
        """
        if not new_title.strip():
            raise ValueError("Chat title cannot be empty.")
        new_title = new_title.strip()[:50]  # Limit to 50 characters
        db: Session = get_db()
        db.execute(
            "UPDATE chats SET title = :title WHERE id = :chat_id",
            {"title": new_title, "chat_id": chat_id}
        )

    @staticmethod
    def get_user_chats(
        user_id: int, limit: int = 10, offset: int = 0
    ) -> List[Dict[str, Union[str, int]]]:
        """
        Retrieve paginated chat history for a user.
        """
        db: Session = get_db()
        chats = db.execute(
            """
            SELECT
                id,
                user_id,
                title,
                model_id,
                created_at as timestamp
            FROM chats
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"user_id": user_id, "limit": limit, "offset": offset}
        ).fetchall()
        return [dict(chat) for chat in chats]

    @staticmethod
    def create(chat_id: str, user_id: int, title: str = "New Chat", model_id: Optional[int] = None) -> None:
        """
        Create a new chat record.

        Args:
            chat_id: The unique identifier for the chat
            user_id: The ID of the user creating the chat
            title: The chat title (defaults to "New Chat")
            model_id: Optional ID of the model to use for this chat
        """
        if len(title) > 50:
            title = title[:50]
        db: Session = get_db()
        db.execute(
            "INSERT INTO chats (id, user_id, title, model_id) VALUES (:chat_id, :user_id, :title, :model_id)",
            {"chat_id": chat_id, "user_id": user_id, "title": title, "model_id": model_id}
        )
        logger.info("Chat created: %s for user %d with model %s", chat_id, user_id, model_id or "default")

    @staticmethod
    def delete(chat_id: str) -> None:
        """
        Delete a chat and its associated messages efficiently.
        """
        db: Session = get_db()
        db.execute("PRAGMA foreign_keys = ON;")  # Enable cascading deletion
        db.execute("DELETE FROM chats WHERE id = :chat_id", {"chat_id": chat_id})
        logger.info("Chat deleted: %s", chat_id)

    @staticmethod
    def get_model(chat_id: str) -> Optional[int]:
        """
        Retrieve the model ID associated with a given chat.

        Returns:
            The model_id if set, otherwise None.
        """
        db: Session = get_db()
        row = db.execute(
            "SELECT model_id FROM chats WHERE id = :chat_id",
            {"chat_id": chat_id}
        ).fetchone()
        return row["model_id"] if row else None


@dataclass
class UploadedFile:
    """
    Represents an uploaded file associated with a chat.
    """

    id: int
    chat_id: str
    filename: str
    filepath: str

    @staticmethod
    def create(chat_id: str, filename: str, filepath: str) -> None:
        """
        Insert a new uploaded file record into the database.
        """
        db: Session = get_db()
        db.execute(
            "INSERT INTO uploaded_files (chat_id, filename, filepath) VALUES (:chat_id, :filename, :filepath)",
            {"chat_id": chat_id, "filename": filename, "filepath": filepath}
        )

    @staticmethod
    def get_by_chat_and_filename(
        chat_id: str, filename: str
    ) -> Optional["UploadedFile"]:
        """
        Retrieve an uploaded file by chat ID and filename.
        """
        db: Session = get_db()
        row = db.execute(
            "SELECT * FROM uploaded_files WHERE chat_id = :chat_id AND filename = :filename",
            {"chat_id": chat_id, "filename": filename}
        ).fetchone()
        if row:
            return UploadedFile(**dict(row))
        return None

    @staticmethod
    def delete_by_chat_ids(chat_ids: List[str]) -> None:
        """
        Delete all uploaded files associated with specific chat IDs.
        """
        if not chat_ids:
            return
        db: Session = get_db()
        placeholders = ",".join(f":id{i}" for i in range(len(chat_ids)))
        params = {f"id{i}": chat_id for i, chat_id in enumerate(chat_ids)}
        query = f"DELETE FROM uploaded_files WHERE chat_id IN ({placeholders})"
        db.execute(query, params)
        logger.info("Deleted uploaded files for chats: %s", ", ".join(map(str, chat_ids)))
