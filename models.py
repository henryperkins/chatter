"""
models.py

This module contains classes and methods for managing users, models,
chats, and files in the database.
"""

import logging
import os
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Optional, List, Dict, Union, Any, Mapping

from database import db_connection  # Use the centralized context manager
import requests

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
        with db_connection() as db:
            user_row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
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
    temperature: float = 1.0
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
        with db_connection() as db:
            row = db.execute("SELECT * FROM models WHERE is_default = 1").fetchone()
            if row:
                return Model(**dict(row))
            return None

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.
        """
        with db_connection() as db:
            row = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
            if row:
                return Model(**dict(row))
            return None

    @staticmethod
    def get_all(limit: int = 10, offset: int = 0) -> List["Model"]:
        """
        Retrieve all models from the database, optionally paginated.
        """
        with db_connection() as db:
            rows = db.execute(
                "SELECT * FROM models ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [Model(**dict(row)) for row in rows]

    @staticmethod
    def set_default(model_id: int):
        """
        Set a model as the default, and remove the default status from any other model.
        """
        with db_connection() as db:
            # Reset the current default model
            db.execute("UPDATE models SET is_default = 0 WHERE is_default = 1")

            # Set the new model as default
            db.execute("UPDATE models SET is_default = 1 WHERE id = ?", (model_id,))

            # Ensure only one default model exists
            duplicate_check = db.execute(
                "SELECT COUNT(*) as count FROM models WHERE is_default = 1"
            ).fetchone()
            if duplicate_check["count"] > 1:
                raise ValueError("More than one default model exists.")

            logger.info("Model set as default (ID %d)", model_id)

    @staticmethod
    def create(data: Dict[str, Any]) -> int:
        """
        Create a new model record in the database.

        Args:
            data (dict): A dictionary containing model attributes.

        Returns:
            int: The ID of the newly created model.
        """
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                """
                INSERT INTO models (
                    name,
                    deployment_name,
                    description,
                    api_endpoint,
                    api_version,
                    temperature,
                    max_tokens,
                    max_completion_tokens,
                    model_type,
                    requires_o1_handling,
                    is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data['name'],
                    data['deployment_name'],
                    data.get('description', ''),
                    data['api_endpoint'],
                    data['api_version'],
                    data['temperature'],
                    data.get('max_tokens'),
                    data['max_completion_tokens'],
                    data['model_type'],
                    data.get('requires_o1_handling', False),
                    data.get('is_default', False),
                )
            )
            model_id = cursor.lastrowid

            # If the new model is set as default, unset default on other models
            if data.get('is_default', False):
                db.execute(
                    "UPDATE models SET is_default = 0 WHERE id != ?",
                    (model_id,)
                )

            logger.info("Model created with ID: %d", model_id)
            return model_id

    @staticmethod
    def update(model_id: int,  Mapping[str, Any]) -> None:
        """
        Update an existing model's attributes in the database.

        Args:
            model_id (int): The ID of the model to update.
            data (dict): A dictionary containing the updated model attributes.
        """
        with db_connection() as db:
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
            set_clause = ", ".join(f"{key} = ?" for key in data)
            placeholders = list(data.values())
            placeholders.append(model_id)  # Add model_id for the WHERE clause

            # 5. Execute the update
            db.execute(
                f"""
                UPDATE models
                SET {set_clause}
                WHERE id = ?
                """,
                tuple(placeholders),
            )

            # 6. Handle default model logic (if applicable)
            if data.get("is_default"):
                db.execute("UPDATE models SET is_default = 0 WHERE id != ?", (model_id,))

            logger.info("Model updated (ID %d)", model_id)

    @staticmethod
    def validate_model_config(config: Mapping[str, Any]) -> None:
        """
        Validate the required fields for a model configuration.

        Raises:
            ValueError: If a required field is missing or invalid.
        """
        required_fields = [
            "name", "deployment_name", "api_endpoint", "api_version",
            "model_type", "max_completion_tokens"
        ]

        for field_name in required_fields:
            val = config.get(field_name)
            if not val:
                raise ValueError(f"Missing required field: {field_name}")

        # Validate API endpoint
        api_endpoint = config["api_endpoint"]
        if not api_endpoint.startswith("https://") or "openai.azure.com" not in api_endpoint:
            raise ValueError("Invalid Azure OpenAI API endpoint.")

        # Validate temperature
        temperature = config.get("temperature", 1.0)
        if not (0 <= float(temperature) <= 2):
            raise ValueError("Temperature must be between 0 and 2.")

        # Validate max_tokens
        max_tokens = config.get("max_tokens", None)
        if max_tokens is not None and (int(max_tokens) <= 0):
            raise ValueError("Max tokens must be a positive integer.")


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
        with db_connection() as db:
            chat = db.execute(
                "SELECT id FROM chats WHERE id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            return chat is not None

    @staticmethod
    def is_title_default(chat_id: str) -> bool:
        """
        Check whether a chat has the default title.
        """
        with db_connection() as db:
            row = db.execute("SELECT title FROM chats WHERE id = ?", (chat_id,)).fetchone()
            return bool(row) and row["title"] == "New Chat"

    @staticmethod
    def update_title(chat_id: str, new_title: str) -> None:
        """
        Update the title of a chat with validation.
        """
        if not new_title.strip():
            raise ValueError("Chat title cannot be empty.")
        new_title = new_title.strip()[:50]  # Limit to 50 characters
        with db_connection() as db:
            db.execute(
                "UPDATE chats SET title = ? WHERE id = ?",
                (new_title, chat_id),
            )

    @staticmethod
    def get_user_chats(user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Union[str, int]]]:
        """
        Retrieve paginated chat history for a user.
        """
        with db_connection() as db:
            chats = db.execute(
                """
                SELECT * FROM chats 
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
            return [dict(chat) for chat in chats]

    @staticmethod
    def create(chat_id: str, user_id: int, title: str = "New Chat") -> None:
        """
        Create a new chat record.
        """
        if len(title) > 50:
            title = title[:50]
        with db_connection() as db:
            db.execute(
                "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
                (chat_id, user_id, title),
            )
            logger.info("Chat created: %s for user %d", chat_id, user_id)

    @staticmethod
    def delete(chat_id: str) -> None:
        """
        Delete a chat and its associated messages efficiently.
        """
        with db_connection() as db:
            db.execute("PRAGMA foreign_keys = ON;")  # Enable cascading deletion
            db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            logger.info("Chat deleted: %s", chat_id)

    @staticmethod
    def get_model(chat_id: str) -> Optional[int]:
        """
        Retrieve the model ID associated with a given chat.
        
        Returns:
            The model_id if set, otherwise None.
        """
        with db_connection() as db:
            row = db.execute(
                "SELECT model_id FROM chats WHERE id = ?",
                (chat_id,),
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
        with db_connection() as db:
            db.execute(
                "INSERT INTO uploaded_files (chat_id, filename, filepath) VALUES (?, ?, ?)",
                (chat_id, filename, filepath),
            )

    @staticmethod
    def get_by_chat_and_filename(chat_id: str, filename: str) -> Optional["UploadedFile"]:
        """
        Retrieve an uploaded file by chat ID and filename.
        """
        with db_connection() as db:
            row = db.execute(
                "SELECT * FROM uploaded_files WHERE chat_id = ? AND filename = ?",
                (chat_id, filename),
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
        with db_connection() as db:
            placeholders = ",".join("?" for _ in chat_ids)
            query = f"DELETE FROM uploaded_files WHERE chat_id IN ({placeholders})"
            db.execute(query, chat_ids)
            logger.info("Deleted uploaded files for chats: %s", ", ".join(chat_ids))
