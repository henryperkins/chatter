"""
models.py

This module contains classes and methods for managing users, models,
and chat sessions in the database.
"""

import logging
import os
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Optional, List, Dict, Union, Any

import requests

from database import get_db

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
        db = get_db()
        user_row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_row:
            return User(
                id=user_row["id"],
                username=user_row["username"],
                email=user_row["email"],
                role=user_row["role"],
            )
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

    def __post_init__(self) -> None:
        """
        Validate or adjust fields after dataclass initialization.
        """
        self.id = int(self.id)

    @staticmethod
    def get_default() -> Optional["Model"]:
        """
        Retrieve the default model (where is_default = 1).
        """
        db = get_db()
        row = db.execute("SELECT * FROM models WHERE is_default = 1").fetchone()
        if row:
            return Model(**dict(row))
        return None

    @staticmethod
    def validate_api_endpoint(api_endpoint: str, api_key: Optional[str]) -> bool:
        """
        Validate the given API endpoint and key.

        Raises:
            ValueError: If the endpoint or key is invalid.
        """
        # Ensure we have a proper string.
        if not api_endpoint:
            raise ValueError("API endpoint is required and must be a non-empty string.")

        parsed_url = urlparse(api_endpoint)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid API endpoint URL format.")

        if parsed_url.scheme != "https":
            raise ValueError("API endpoint must use HTTPS.")

        if not parsed_url.netloc.endswith(".openai.azure.com"):
            raise ValueError(
                "API endpoint must be an Azure OpenAI domain (*.openai.azure.com)."
            )

        if not api_key:
            raise ValueError(
                "Azure OpenAI API key not found. "
                "Please set AZURE_OPENAI_KEY environment variable."
            )

        try:
            response = requests.get(
                api_endpoint, headers={"api-key": api_key}, timeout=5
            )
        except requests.RequestException as exc:
            logger.error("API endpoint validation failed: %s", str(exc))
            raise ValueError(
                "Failed to connect to API endpoint: {0}".format(str(exc))
            ) from exc

        if response.status_code == 401:
            raise ValueError("Invalid API key.")
        if response.status_code == 404:
            # Base URL valid even if specific path doesn't exist
            return True
        if response.status_code >= 400:
            raise ValueError(
                "API endpoint validation failed with status {0}".format(
                    response.status_code
                )
            )
        return True

    @staticmethod
    def validate_model_config(
        config: Dict[str, Union[str, int, float, bool, None]]
    ) -> None:
        """
        Validate the required fields for a model configuration.

        Raises:
            ValueError: If a required field is missing or invalid.
        """
        db = get_db()
        required_fields = [
            "name",
            "deployment_name",
            "api_endpoint",
            "api_version",
            "model_type",
            "max_completion_tokens",
        ]
        for field_name in required_fields:
            val = config.get(field_name)
            if not val:
                raise ValueError("Missing required field: {0}".format(field_name))
            if not isinstance(val, str) and field_name in ("name", "deployment_name"):
                raise ValueError("Field {0} must be a string.".format(field_name))

        # Unpack and cast to str to ensure urlparse compatibility
        endpoint_value = str(config["api_endpoint"])

        # Validate uniqueness: name
        row_name = db.execute(
            "SELECT id FROM models WHERE name = ?", (config["name"],)
        ).fetchone()
        if row_name and row_name["id"] != config.get("id"):
            raise ValueError("Model name already exists. Choose a different name.")

        # Validate uniqueness: deployment_name
        row_deploy = db.execute(
            "SELECT id FROM models WHERE deployment_name = ?",
            (config["deployment_name"],),
        ).fetchone()
        if row_deploy and row_deploy["id"] != config.get("id"):
            raise ValueError("Deployment name already exists. Choose a different one.")

        # Validate 'api_version' is a string
        api_version_val = str(config["api_version"])

        valid_api_versions = ["2024-10-01-preview", "2024-12-01-preview"]
        if api_version_val not in valid_api_versions:
            raise ValueError("Invalid API version specified.")

        # Validate 'model_type'
        model_type_val = str(config["model_type"])
        valid_types = ["azure", "openai"]
        if model_type_val not in valid_types:
            raise ValueError("Invalid model_type specified.")

        # Validate temperature
        temp_val = config.get("temperature", 1.0)
        if temp_val is None:
            temp_val = 1.0
        try:
            temperature = float(temp_val)
            if temperature < 0 or temperature > 2:
                raise ValueError("Temperature must be between 0 and 2.")
        except ValueError as exc:
            raise ValueError("Temperature must be a number between 0 and 2.") from exc

        # Validate max_tokens if present
        max_tokens_val = config.get("max_tokens")
        if max_tokens_val is not None:
            try:
                max_tokens = int(max_tokens_val)
                if max_tokens <= 0:
                    raise ValueError("Max tokens must be a positive integer.")
            except ValueError as exc:
                raise ValueError("Max tokens must be a positive integer.") from exc

        # Validate max_completion_tokens
        mc_tokens_val = config["max_completion_tokens"]
        try:
            mc_tokens = int(mc_tokens_val)
            if mc_tokens <= 0:
                raise ValueError("Max completion tokens must be a positive integer.")
        except ValueError as exc:
            raise ValueError(
                "Max completion tokens must be a positive integer."
            ) from exc

        # Validate requires_o1_handling
        o1_val = config.get("requires_o1_handling", False)
        if not isinstance(o1_val, bool):
            raise ValueError("requires_o1_handling must be a boolean.")

        # Validate version
        version_val = config.get("version", 1)
        if version_val is None:
            version_val = 1
        try:
            version_int = int(version_val)
            if version_int <= 0:
                raise ValueError("Version must be a positive integer.")
        except ValueError as exc:
            raise ValueError("Version must be a positive integer.") from exc

        # Finally, check API endpoint connectivity
        api_key = os.getenv("AZURE_OPENAI_KEY")
        Model.validate_api_endpoint(endpoint_value, api_key)

    @staticmethod
    def get_all(limit: int = 10, offset: int = 0) -> List["Model"]:
        """
        Retrieve all models from the database, optionally with limit/offset.
        """
        db = get_db()
        rows = db.execute(
            """
            SELECT * FROM models
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [Model(**dict(r)) for r in rows]

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.
        """
        db = get_db()
        row = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        if row:
            return Model(**dict(row))
        return None

    @staticmethod
    def is_model_in_use(model_id: int) -> bool:
        """
        Check whether a model is currently in use (default or assigned to any chat).
        """
        db = get_db()
        default_row = db.execute(
            "SELECT id FROM models WHERE is_default = 1"
        ).fetchone()
        if default_row and default_row["id"] == model_id:
            return True

        count_row = db.execute(
            "SELECT COUNT(*) as c FROM chats WHERE model_id = ?",
            (model_id,),
        ).fetchone()
        if count_row and count_row["c"] > 0:
            return True
        return False

    @staticmethod
    def get_immutable_fields(model_id: int) -> List[str]:
        """
        Return a list of fields that cannot be changed if the model is in use.
        """
        if Model.is_model_in_use(model_id):
            return [
                "name",
                "deployment_name",
                "api_endpoint",
                "api_version",
                "model_type",
            ]
        return []

    @staticmethod
    def create(config: Dict[str, Union[str, int, float, bool, None]]) -> int:
        """
        Create a new model using the provided config.

        Returns:
            int: The newly-created model's ID.
        """
        Model.validate_model_config(config)
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO models
            (
                name, deployment_name, description, model_type, api_endpoint,
                temperature, max_tokens, max_completion_tokens, is_default,
                requires_o1_handling, api_version, version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                config["name"],
                config["deployment_name"],
                config.get("description", ""),
                str(config["model_type"]),
                str(config["api_endpoint"]),
                float(config.get("temperature", 1.0)),
                (int(config["max_tokens"]) if config.get("max_tokens") else None),
                int(config["max_completion_tokens"]),
                bool(config.get("is_default", False)),
                bool(config.get("requires_o1_handling", False)),
                str(config["api_version"]),
                int(config.get("version", 1)),
            ),
        )
        model_id_val: Any = cursor.lastrowid
        db.commit()

        if model_id_val is None:
            raise ValueError("Model creation failed; no ID returned.")

        model_id_int = int(model_id_val)
        logger.info("Model created: %s (ID %d)", config["name"], model_id_int)
        return model_id_int

    @staticmethod
    def update(
        model_id: int, config: Dict[str, Union[str, int, float, bool, None]]
    ) -> None:
        """
        Update an existing model. If the model is in use, certain fields cannot change.
        """
        Model.validate_model_config(config)
        db = get_db()

        current_model = Model.get_by_id(model_id)
        if not current_model:
            raise ValueError("Model not found.")

        # If the model is in use, ensure certain fields remain unchanged
        if Model.is_model_in_use(model_id):
            immutables = Model.get_immutable_fields(model_id)
            for f_name in immutables:
                current_val = getattr(current_model, f_name)
                new_val = config[f_name]
                if str(current_val) != str(new_val):
                    raise ValueError(
                        "Cannot change '{0}' of a model in use.".format(f_name)
                    )

        new_version = current_model.version + 1
        db.execute(
            """
            UPDATE models
            SET
                name = ?,
                deployment_name = ?,
                description = ?,
                model_type = ?,
                api_endpoint = ?,
                temperature = ?,
                max_tokens = ?,
                max_completion_tokens = ?,
                is_default = ?,
                requires_o1_handling = ?,
                api_version = ?,
                version = ?
            WHERE id = ?
            """,
            (
                config["name"],
                config["deployment_name"],
                config.get("description", ""),
                str(config["model_type"]),
                str(config["api_endpoint"]),
                float(config.get("temperature", 1.0)),
                (int(config["max_tokens"]) if config.get("max_tokens") else None),
                int(config["max_completion_tokens"]),
                bool(config.get("is_default", False)),
                bool(config.get("requires_o1_handling", False)),
                str(config["api_version"]),
                new_version,
                model_id,
            ),
        )
        db.commit()
        logger.info(
            "Model updated: %s (ID %d) to version %d",
            config["name"],
            model_id,
            new_version,
        )

    @staticmethod
    def delete(model_id: int, new_model_id: Optional[int] = None) -> None:
        """
        Delete a model from the database.

        If the model is in use, you must provide a new_model_id to migrate chats.
        """
        if Model.is_model_in_use(model_id):
            if new_model_id is None:
                raise ValueError(
                    "Cannot delete a model in use. Provide a new model ID to migrate chats."
                )
            db = get_db()
            db.execute(
                "UPDATE chats SET model_id = ? WHERE model_id = ?",
                (new_model_id, model_id),
            )
            db.commit()

        db = get_db()
        db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        db.commit()
        logger.info("Model deleted (ID %d)", model_id)

    @staticmethod
    def set_default(model_id: int) -> None:
        """
        Set a model as the default (is_default=1), removing
        the default flag from any previously default model.
        """
        db = get_db()
        current_default = db.execute(
            "SELECT id FROM models WHERE is_default = 1"
        ).fetchone()
        if current_default and current_default["id"] != model_id:
            db.execute(
                "UPDATE models SET is_default = 0 WHERE id = ?",
                (current_default["id"],),
            )

        db.execute("UPDATE models SET is_default = 1 WHERE id = ?", (model_id,))
        db.commit()
        logger.info("Model set as default (ID %d)", model_id)

    @staticmethod
    def get_version_history(
        model_id: int,
    ) -> List[Dict[str, Union[str, int, float, bool]]]:
        """
        Retrieve the version history of a model from `model_versions` table.
        """
        db = get_db()
        versions = db.execute(
            "SELECT * FROM model_versions WHERE model_id = ? ORDER BY version DESC",
            (model_id,),
        ).fetchall()
        return [dict(vr) for vr in versions]

    @staticmethod
    def revert_to_version(model_id: int, version_num: int) -> None:
        """
        Revert a model to a specific version from `model_versions` table.
        """
        db = get_db()
        version_data = db.execute(
            "SELECT * FROM model_versions WHERE model_id = ? AND version = ?",
            (model_id, version_num),
        ).fetchone()
        if not version_data:
            raise ValueError("Version not found.")

        db.execute(
            """
            UPDATE models
            SET
                name = ?,
                deployment_name = ?,
                description = ?,
                model_type = ?,
                api_endpoint = ?,
                temperature = ?,
                max_tokens = ?,
                max_completion_tokens = ?,
                is_default = ?,
                requires_o1_handling = ?,
                api_version = ?,
                version = ?
            WHERE id = ?
            """,
            (
                version_data["name"],
                version_data["deployment_name"],
                version_data["description"],
                version_data["model_type"],
                version_data["api_endpoint"],
                version_data["temperature"],
                version_data["max_tokens"],
                version_data["max_completion_tokens"],
                version_data["is_default"],
                version_data["requires_o1_handling"],
                version_data["api_version"],
                version_data["version"],
                model_id,
            ),
        )
        db.commit()
        logger.info("Model %d reverted to version %d", model_id, version_num)


@dataclass
class Chat:
    """
    Represents a chat session in the system.
    """

    id: str
    user_id: int
    title: str
    model_id: Optional[int] = None

    def __post_init__(self) -> None:
        """Ensure user_id is an integer."""
        self.user_id = int(self.user_id)

    @staticmethod
    def get_model(chat_id: str) -> Optional[int]:
        """
        Get the model_id for a given chat, if any.
        """
        db = get_db()
        row = db.execute(
            "SELECT model_id FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
        if row:
            return row["model_id"]
        return None

    @staticmethod
    def set_model(chat_id: str, model_id: int) -> None:
        """
        Associate or switch the model for a given chat.
        """
        db = get_db()
        db.execute("UPDATE chats SET model_id = ? WHERE id = ?", (model_id, chat_id))
        db.commit()
        logger.info("Model set for chat %s: Model ID %d", chat_id, model_id)

    @staticmethod
    def get_by_id(chat_id: str) -> Optional["Chat"]:
        """
        Retrieve a chat by its ID.
        """
        db = get_db()
        row = db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if row:
            return Chat(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                model_id=row.get("model_id"),
            )
        return None

    @staticmethod
    def get_user_chats(user_id: int) -> List[Dict[str, Union[str, int]]]:
        """
        Retrieve all chats for a given user in descending order of creation.
        """
        db = get_db()
        chat_rows = db.execute(
            "SELECT * FROM chats WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(cr) for cr in chat_rows]

    @staticmethod
    def create(chat_id: str, user_id: int, title: str) -> None:
        """
        Create a new chat record in the database.
        """
        db = get_db()
        db.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, user_id, title),
        )
        db.commit()
        logger.info("Chat created: %s for user %d", chat_id, user_id)


@dataclass
class UploadedFile:
    """Represents an uploaded file associated with a chat."""

    id: int
    chat_id: str
    filename: str
    filepath: str

    @staticmethod
    def create(chat_id: str, filename: str, filepath: str) -> None:
        """Insert a new uploaded file record into the database."""
        db = get_db()
        db.execute(
            "INSERT INTO uploaded_files (chat_id, filename, filepath) VALUES (?, ?, ?)",
            (chat_id, filename, filepath)
        )
        db.commit()

    @staticmethod
    def get_by_chat_and_filename(chat_id: str, filename: str) -> Optional['UploadedFile']:
        """Retrieve an uploaded file by chat ID and filename."""
        db = get_db()
        row = db.execute(
            "SELECT * FROM uploaded_files WHERE chat_id = ? AND filename = ?",
            (chat_id, filename)
        ).fetchone()
        if row:
            return UploadedFile(
                id=row['id'],
                chat_id=row['chat_id'],
                filename=row['filename'],
                filepath=row['filepath']
            )
        return None
