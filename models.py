# models.py

import logging
from dataclasses import dataclass
from typing import Optional, List, Union, Any, Dict
from datetime import datetime

from database import get_db  # Use SQLAlchemy session manager
from sqlalchemy.orm import Session
from sqlalchemy import text

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
        Retrieve a user by ID from the database.        """
        db: Session = get_db()
        try:
            query = text("SELECT * FROM users WHERE id = :user_id")
            if user_row := db.execute(query, {"user_id": user_id}).fetchone():
                # Convert SQLAlchemy row to dictionary using index access
                user_dict = {
                    'id': user_row[0],
                    'username': user_row[1],
                    'email': user_row[2],
                    'role': user_row[3]
                }
                logger.debug(f"User retrieved: {user_dict}")
                return User(**user_dict)
            logger.info(f"No user found with ID: {user_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving user by ID {user_id}: {e}")
            raise
        finally:
            db.close()

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
        try:
            query = text("SELECT * FROM models WHERE is_default = :is_default")
            if row := db.execute(query, {"is_default": True}).fetchone():
                # Convert SQLAlchemy row to dictionary using index access
                model_dict = {
                    'id': row[0],
                    'name': row[1],
                    'deployment_name': row[2],
                    'description': row[3],
                    'model_type': row[4],
                    'api_endpoint': row[5],
                    'api_key': row[6],
                    'temperature': row[7],
                    'max_tokens': row[8],
                    'max_completion_tokens': row[9],
                    'is_default': row[10],
                    'requires_o1_handling': row[11],
                    'api_version': row[12],
                    'version': row[13],
                    'created_at': row[14]
                }
                logger.debug(f"Default model retrieved: {model_dict}")
                return Model(**model_dict)
            logger.info("No default model found.")
            return None
        except Exception as e:
            logger.error(f"Error retrieving default model: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.
        """
        db: Session = get_db()
        try:
            query = text("SELECT * FROM models WHERE id = :model_id")
            if row := db.execute(query, {"model_id": model_id}).fetchone():
                # Convert SQLAlchemy row to dictionary using index access
                model_dict = {
                    'id': row[0],
                    'name': row[1],
                    'deployment_name': row[2],
                    'description': row[3],
                    'model_type': row[4],
                    'api_endpoint': row[5],
                    'api_key': row[6],
                    'temperature': row[7],
                    'max_tokens': row[8],
                    'max_completion_tokens': row[9],
                    'is_default': row[10],
                    'requires_o1_handling': row[11],
                    'api_version': row[12],
                    'version': row[13],
                    'created_at': row[14]
                }
                logger.debug(f"Model retrieved by ID {model_id}: {model_dict}")
                return Model(**model_dict)
            logger.info(f"No model found with ID: {model_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving model by ID {model_id}: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def get_all(limit: int = 10, offset: int = 0) -> List["Model"]:
        """
        Retrieve all models from the database, optionally paginated.
        """
        db: Session = get_db()
        try:
            query = text("""
                SELECT * FROM models 
                ORDER BY created_at DESC 
                LIMIT :limit OFFSET :offset
            """)
            rows = db.execute(query, {"limit": limit, "offset": offset}).fetchall()
            models = []
            for row in rows:
                # Convert SQLAlchemy row to dictionary using index access
                model_dict = {
                    'id': row[0],
                    'name': row[1],
                    'deployment_name': row[2],
                    'description': row[3],
                    'model_type': row[4],
                    'api_endpoint': row[5],
                    'api_key': row[6],
                    'temperature': row[7],
                    'max_tokens': row[8],
                    'max_completion_tokens': row[9],
                    'is_default': row[10],
                    'requires_o1_handling': row[11],
                    'api_version': row[12],
                    'version': row[13],
                    'created_at': row[14]
                }
                models.append(Model(**model_dict))
            logger.debug(f"Retrieved {len(models)} models with limit={limit} and offset={offset}")
            return models
        except Exception as e:
            logger.error(f"Error retrieving all models: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def set_default(model_id: int):
        """
        Set a model as the default, and remove the default status from any other model.
        """
        db: Session = get_db()
        try:
            # Begin transaction
            db.execute(text("UPDATE models SET is_default = 0 WHERE is_default = :current_default"), {"current_default": True})
            db.execute(text("UPDATE models SET is_default = 1 WHERE id = :model_id"), {"model_id": model_id})

            # Ensure only one default model exists
            duplicate_check = db.execute(text("""
                SELECT COUNT(*) as count FROM models WHERE is_default = :is_default
            """), {"is_default": True}).fetchone()
            if duplicate_check and duplicate_check[0] > 1:
                raise ValueError("More than one default model exists.")

            db.commit()
            logger.info(f"Model set as default (ID {model_id})")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to set default model {model_id}: {e}")
            raise
        finally:
            db.close()

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
        try:
            # Handle temperature for o1-preview models
            if data.get("requires_o1_handling", False):
                data["temperature"] = None

            query = text("""
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
                RETURNING id
            """)
            result = db.execute(query, {
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
            })
            model_id = result.scalar()
            if model_id is None:
                logger.error("Failed to create model - no ID returned")
                return None

            # If the new model is set as default, unset default on other models
            if data.get("is_default", False):
                unset_default_query = text("""
                    UPDATE models 
                    SET is_default = 0 
                    WHERE id != :model_id AND is_default = :is_default
                """)
                db.execute(unset_default_query, {"model_id": model_id, "is_default": True})
                db.commit()

            logger.info(f"Model created with ID: {model_id}")
            return model_id
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create model: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def update(model_id: int, data: Dict[str, Any]) -> None:
        """
        Update an existing model's attributes.

        Args:
            model_id (int): The ID of the model to update.
            data (dict): A dictionary containing the attributes to update.
        """
        db: Session = get_db()
        try:
            # Validate the data
            Model.validate_model_config(data)

            # Fetch the existing model
            model = Model.get_by_id(model_id)
            if not model:
                raise ValueError(f"Model with ID {model_id} not found.")

            # Update model attributes
            allowed_fields = {
                'name', 'deployment_name', 'description', 'api_endpoint',
                'api_key', 'api_version', 'temperature', 'max_tokens',
                'max_completion_tokens', 'model_type', 'requires_o1_handling',
                'is_default', 'version'
            }
            update_data = {key: value for key, value in data.items() if key in allowed_fields}

            if not update_data:
                logger.info(f"No valid fields to update for model ID {model_id}")
                return

            set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
            params = {**update_data, "model_id": model_id}

            query = text(f"""
                UPDATE models
                SET {set_clause}
                WHERE id = :model_id
            """)

            db.execute(query, params)

            # Handle default model logic (if applicable)
            if update_data.get("is_default", False):
                unset_default_query = text("""
                    UPDATE models 
                    SET is_default = 0 
                    WHERE id != :model_id AND is_default = :is_default
                """)
                db.execute(unset_default_query, {"model_id": model_id, "is_default": True})

            db.commit()
            logger.info(f"Model updated (ID {model_id})")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update model {model_id}: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def validate_model_config(config: Dict[str, Any]) -> None:
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
        max_tokens = config.get("max_tokens")
        if max_tokens is not None and (int(max_tokens) <= 0):
            raise ValueError("Max tokens must be a positive integer.")

        # Add validation for max_completion_tokens
        if config.get('max_completion_tokens') and not (1 <= config['max_completion_tokens'] <= 16384):
            raise ValueError("max_completion_tokens must be between 1 and 16384")

    @staticmethod
    def cleanup_orphaned_files() -> None:
        """Remove files without database references"""
        # TODO: Implement file cleanup logic using `text()`
        pass

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
        db: Session = get_db()
        try:
            query = text("""
                SELECT c.*, m.name as model_name 
                FROM chats c 
                LEFT JOIN models m ON c.model_id = m.id 
                WHERE c.user_id = :user_id 
                ORDER BY c.created_at DESC 
                LIMIT :limit OFFSET :offset
            """)
            result = db.execute(query, {"user_id": user_id, "limit": limit, "offset": offset}).fetchall()
            logger.debug(f"Retrieved {len(result)} chats for user ID {user_id}")
            return result
        except Exception as e:
            logger.error(f"Error retrieving chats for user {user_id}: {e}")
            raise
        finally:
            db.close()


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
        try:
            query = text("""
                SELECT id FROM chats 
                WHERE id = :chat_id AND user_id = :user_id
            """)
            chat = db.execute(query, {"chat_id": chat_id, "user_id": user_id}).fetchone()
            ownership = chat is not None
            logger.debug(f"Ownership check for chat_id {chat_id} and user_id {user_id}: {ownership}")
            return ownership
        except Exception as e:
            logger.error(f"Error checking ownership for chat_id {chat_id}: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def is_title_default(chat_id: str) -> bool:
        """
        Check whether a chat has the default title.
        """
        db: Session = get_db()
        try:
            query = text("SELECT title FROM chats WHERE id = :chat_id")
            row = db.execute(query, {"chat_id": chat_id}).fetchone()
            is_default = bool(row) and row[0] == "New Chat"
            logger.debug(f"Title default check for chat_id {chat_id}: {is_default}")
            return is_default
        except Exception as e:
            logger.error(f"Error checking title for chat_id {chat_id}: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def update_title(chat_id: str, new_title: str) -> None:
        """
        Update the title of a chat with validation.
        """
        if not new_title.strip():
            raise ValueError("Chat title cannot be empty.")
        new_title = new_title.strip()[:50]  # Limit to 50 characters

        db: Session = get_db()
        try:
            query = text("""
                UPDATE chats 
                SET title = :title 
                WHERE id = :chat_id
            """)
            db.execute(query, {"title": new_title, "chat_id": chat_id})
            db.commit()
            logger.info(f"Chat title updated for chat_id {chat_id} to '{new_title}'")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update chat title for chat_id {chat_id}: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def get_user_chats(user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Union[str, int]]]:
        """
        Retrieve paginated chat history for a user.
        """
        db: Session = get_db()
        try:
            query = text("""
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
            """)
            chats = db.execute(query, {"user_id": user_id, "limit": limit, "offset": offset}).fetchall()
            chat_list = []
            for chat in chats:
                chat_dict = {
                    'id': chat[0],
                    'user_id': chat[1],
                    'title': chat[2],
                    'model_id': chat[3],
                    'timestamp': datetime.strptime(chat[4], '%Y-%m-%d %H:%M:%S') if chat[4] else None
                }
                chat_list.append(chat_dict)
            logger.debug(f"Retrieved {len(chat_list)} chats for user_id {user_id}")
            return chat_list
        except Exception as e:
            logger.error(f"Error retrieving chats for user_id {user_id}: {e}")
            raise
        finally:
            db.close()

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
        try:
            query = text("""
                INSERT INTO chats (id, user_id, title, model_id) 
                VALUES (:chat_id, :user_id, :title, :model_id)
            """)
            db.execute(query, {
                "chat_id": chat_id,
                "user_id": user_id,
                "title": title,
                "model_id": model_id
            })
            db.commit()
            logger.info(f"Chat created: {chat_id} for user {user_id} with model {model_id or 'default'}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create chat {chat_id}: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def delete(chat_id: str) -> None:
        """
        Delete a chat and its associated messages efficiently.
        """
        db: Session = get_db()
        try:
            # Enable foreign key constraints if using SQLite
            # Note: For other DBs, this might not be necessary or should be handled differently
            pragma_query = text("PRAGMA foreign_keys = ON;")
            db.execute(pragma_query)

            delete_query = text("DELETE FROM chats WHERE id = :chat_id")
            db.execute(delete_query, {"chat_id": chat_id})
            db.commit()
            logger.info(f"Chat deleted: {chat_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete chat {chat_id}: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def get_model(chat_id: str) -> Optional[int]:
        """
        Retrieve the model ID associated with a given chat.

        Returns:
            The model_id if set, otherwise None.
        """
        db: Session = get_db()
        try:
            query = text("SELECT model_id FROM chats WHERE id = :chat_id")
            row = db.execute(query, {"chat_id": chat_id}).fetchone()
            model_id = row[0] if row else None
            logger.debug(f"Model ID for chat_id {chat_id}: {model_id}")
            return model_id
        except Exception as e:
            logger.error(f"Error retrieving model for chat_id {chat_id}: {e}")
            raise
        finally:
            db.close()


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
        try:
            query = text("""
                INSERT INTO uploaded_files (chat_id, filename, filepath) 
                VALUES (:chat_id, :filename, :filepath)
            """)
            db.execute(query, {
                "chat_id": chat_id,
                "filename": filename,
                "filepath": filepath
            })
            db.commit()
            logger.info(f"File uploaded: {filename} for chat {chat_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create uploaded file record: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def get_by_chat_and_filename(chat_id: str, filename: str) -> Optional["UploadedFile"]:
        """
        Retrieve an uploaded file by chat ID and filename.
        """
        db: Session = get_db()
        try:
            query = text("""
                SELECT * FROM uploaded_files 
                WHERE chat_id = :chat_id AND filename = :filename
            """)
            if row := db.execute(query, {
                "chat_id": chat_id,
                "filename": filename
            }).fetchone():
                file_dict = {
                    'id': row[0],
                    'chat_id': row[1],
                    'filename': row[2],
                    'filepath': row[3]
                }
                return UploadedFile(**file_dict)
            return None
        except Exception as e:
            logger.error(f"Error retrieving uploaded file: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def delete_by_chat_ids(chat_ids: List[str]) -> None:
        """
        Delete all uploaded files associated with specific chat IDs.
        """
        if not chat_ids:
            return
        db: Session = get_db()
        try:
            placeholders = ",".join(f":id{i}" for i in range(len(chat_ids)))
            params = {f"id{i}": chat_id for i, chat_id in enumerate(chat_ids)}
            query = text(f"DELETE FROM uploaded_files WHERE chat_id IN ({placeholders})")
            db.execute(query, params)
            db.commit()
            logger.info("Deleted uploaded files for chats: %s", ", ".join(map(str, chat_ids)))
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting uploaded files: {e}")
            raise
        finally:
            db.close()
