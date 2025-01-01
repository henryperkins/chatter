"""
models.py

This module contains classes and methods for managing users, models, and chat sessions in the database.
"""

from database import get_db
import logging
import re
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Optional

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
    def get_by_id(user_id):
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user:
            return User(user["id"], user["username"], user["email"], user["role"])
        return None

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
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

    def __post_init__(self):
        # Ensure id is an integer
        self.id = int(self.id)

    @staticmethod
    def get_default():
        db = get_db()
        model = db.execute("SELECT * FROM models WHERE is_default = 1").fetchone()
        if model:
            return Model(**dict(model))
        return None

    @staticmethod
    def validate_model_config(config):
        """
        Validates the required fields for a model configuration.

        Args:
            config (dict): Dictionary containing model configuration.

        Raises:
            ValueError: If a required field is missing or invalid.
        """
        required_fields = [
            "name",
            "deployment_name",
            "api_endpoint",
            "api_version",
            "model_type",
            "max_completion_tokens",
        ]
        for field in required_fields:
            if field not in config or not config[field]:
                raise ValueError(f"Missing required field: {field}")

        # Validate 'name'
        if not re.match(r'^[\w\s\-]+$', config["name"]):
            raise ValueError("Model name can only contain letters, numbers, spaces, underscores, and hyphens.")

        # Validate 'deployment_name'
        if not re.match(r'^[\w\-]+$', config["deployment_name"]):
            raise ValueError("Deployment name can only contain letters, numbers, underscores, and hyphens.")

        # Validate 'api_endpoint'
        parsed_url = urlparse(config["api_endpoint"])
        if not all([parsed_url.scheme, parsed_url.netloc]):
            raise ValueError("Invalid API endpoint URL.")

        # Validate 'api_version'
        valid_api_versions = ["2024-10-01-preview", "2024-12-01-preview"]
        if config["api_version"] not in valid_api_versions:
            raise ValueError("Invalid API version specified.")

        # Validate 'model_type'
        valid_model_types = ["azure", "openai"]
        if config["model_type"] not in valid_model_types:
            raise ValueError("Invalid model_type specified.")

        # Validate 'temperature'
        try:
            temperature = float(config.get("temperature", 1.0))
            if not (0 <= temperature <= 2):
                raise ValueError("Temperature must be between 0 and 2")
        except ValueError:
            raise ValueError("Temperature must be a number between 0 and 2")

        # Validate 'max_tokens'
        if "max_tokens" in config and config["max_tokens"] is not None:
            try:
                max_tokens = int(config["max_tokens"])
                if max_tokens <= 0:
                    raise ValueError("Max tokens must be a positive integer")
            except ValueError:
                raise ValueError("Max tokens must be a positive integer")

        # Validate 'max_completion_tokens'
        try:
            max_completion_tokens = int(config["max_completion_tokens"])
            if max_completion_tokens <= 0:
                raise ValueError("Max completion tokens must be a positive integer")
        except ValueError:
            raise ValueError("Max completion tokens must be a positive integer")

        # Validate 'requires_o1_handling'
        if not isinstance(config.get("requires_o1_handling", False), bool):
            raise ValueError("requires_o1_handling must be a boolean.")

        # Validate 'version'
        if "version" in config:
            try:
                version = int(config["version"])
                if version <= 0:
                    raise ValueError("Version must be a positive integer.")
            except ValueError:
                raise ValueError("Version must be a positive integer.")

    @staticmethod
    def get_all(limit=10, offset=0):
        db = get_db()
        models = db.execute(
            "SELECT * FROM models ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [Model(**dict(model)) for model in models]

    @staticmethod
    def get_by_id(model_id):
        db = get_db()
        model = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        if model:
            return Model(**dict(model))
        return None

    @staticmethod
    def is_model_in_use(model_id):
        db = get_db()
        # Check if the model is default
        default_model = db.execute("SELECT id FROM models WHERE is_default = 1").fetchone()
        if default_model and default_model["id"] == model_id:
            return True

        # Check if the model is associated with any chats
        chat_count = db.execute(
            "SELECT COUNT(*) FROM chats WHERE model_id = ?", (model_id,)
        ).fetchone()[0]
        return chat_count > 0

    @staticmethod
    def create(config):
        Model.validate_model_config(config)
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO models
            (name, deployment_name, description, model_type, api_endpoint, temperature, max_tokens,
             max_completion_tokens, is_default, requires_o1_handling, api_version, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                config["name"],
                config["deployment_name"],
                config.get("description", ""),
                config.get("model_type", "azure"),
                config["api_endpoint"],
                float(config.get("temperature", 1.0)),
                int(config.get("max_tokens")) if config.get("max_tokens") else None,
                int(config["max_completion_tokens"]),
                bool(config.get("is_default", 0)),
                bool(config.get("requires_o1_handling", 0)),
                config["api_version"],
                int(config.get("version", 1)),
            ),
        )
        model_id = cursor.lastrowid
        db.commit()
        logger.info(f"Model created: {config['name']} with ID {model_id}")
        return model_id

    @staticmethod
    def update(model_id, config):
        Model.validate_model_config(config)
        db = get_db()
        # Fetch current model data
        current_model = Model.get_by_id(model_id)
        if not current_model:
            raise ValueError("Model not found.")

        # Check if the model is in use and prevent changing critical fields if so
        if Model.is_model_in_use(model_id):
            immutable_fields = [
                "name",
                "deployment_name",
                "api_endpoint",
                "api_version",
                "model_type",
            ]
            for field in immutable_fields:
                if getattr(current_model, field) != config[field]:
                    raise ValueError(f"Cannot change '{field}' of a model that is in use.")

        # Increment version if any changes are made
        new_version = current_model.version + 1

        db.execute(
            """
            UPDATE models SET
                name = ?, deployment_name = ?, description = ?, model_type = ?, api_endpoint = ?, temperature = ?,
                max_tokens = ?, max_completion_tokens = ?, is_default = ?, requires_o1_handling = ?, api_version = ?, version = ?
            WHERE id = ?
            """,
            (
                config["name"],
                config["deployment_name"],
                config.get("description", ""),
                config.get("model_type", "azure"),
                config["api_endpoint"],
                float(config.get("temperature", 1.0)),
                int(config.get("max_tokens")) if config.get("max_tokens") else None,
                int(config["max_completion_tokens"]),
                bool(config.get("is_default", 0)),
                bool(config.get("requires_o1_handling", 0)),
                config["api_version"],
                new_version,
                model_id,
            ),
        )
        db.commit()
        logger.info(f"Model updated: {config['name']} with ID {model_id} to version {new_version}")

    @staticmethod
    def delete(model_id):
        if Model.is_model_in_use(model_id):
            raise ValueError("Cannot delete a model that is in use.")
        db = get_db()
        db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model deleted with ID {model_id}")

    @staticmethod
    def set_default(model_id):
        db = get_db()
        db.execute("UPDATE models SET is_default = 0 WHERE is_default = 1")
        db.execute("UPDATE models SET is_default = 1 WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model set as default: {model_id}")

@dataclass
class Chat:
    """
    Represents a chat session in the system.
    """
    id: str
    user_id: int
    title: str
    model_id: Optional[int] = None

    def __post_init__(self):
        # Ensure user_id is an integer
        self.user_id = int(self.user_id)

    @staticmethod
    def get_model(chat_id):
        db = get_db()
        result = db.execute(
            "SELECT model_id FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
        return result["model_id"] if result else None

    @staticmethod
    def set_model(chat_id, model_id):
        db = get_db()
        db.execute("UPDATE chats SET model_id = ? WHERE id = ?", (model_id, chat_id))
        db.commit()
        logger.info(f"Model set for chat {chat_id}: Model ID {model_id}")

    @staticmethod
    def get_by_id(chat_id):
        db = get_db()
        chat = db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if chat:
            return Chat(
                chat["id"], chat["user_id"], chat["title"], chat.get("model_id")
            )
        return None

    @staticmethod
    def get_user_chats(user_id):
        db = get_db()
        chats = db.execute(
            "SELECT * FROM chats WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(chat) for chat in chats]

    @staticmethod
    def create(chat_id, user_id, title):
        db = get_db()
        db.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, user_id, title),
        )
        db.commit()
        logger.info(f"Chat created: {chat_id} for user {user_id}")