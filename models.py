"""
models.py

This module contains classes and methods for managing users, models, and chat sessions in the database.
"""

from database import get_db
import logging

logger = logging.getLogger(__name__)


class User:
    """
    Represents a user in the system.

    Attributes:
        id (int): Unique identifier for the user.
        username (str): Username of the user.
        email (str): Email address of the user.
        role (str): Role of the user (default is "user").
    """

    def __init__(self, id, username, email, role="user"):
        """
        Initializes a User instance.

        Args:
            id (int): User ID (converted to integer for consistency).
            username (str): Username of the user.
            email (str): Email address of the user.
            role (str): Role of the user (default is "user").
        """
        self.id = int(id)  # Ensure id is an integer
        self.username = username
        self.email = email
        self.role = role

    @staticmethod
    def get_by_id(user_id):
        """
        Fetches a user from the database by their ID.

        Args:
            user_id (int): ID of the user to retrieve.

        Returns:
            User: A User object if found, otherwise None.
        """
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user:
            return User(user["id"], user["username"], user["email"], user["role"])
        return None

    @property
    def is_authenticated(self):
        """
        Checks if the user is authenticated.

        Returns:
            bool: True if the user is authenticated.
        """
        return True

    @property
    def is_active(self):
        """
        Checks if the user is active.

        Returns:
            bool: True if the user is active.
        """
        return True

    @property
    def is_anonymous(self):
        """
        Checks if the user is anonymous.

        Returns:
            bool: False as this model does not support anonymous users.
        """
        return False

    def get_id(self):
        """
        Retrieves the user's ID as a string.

        Returns:
            str: User ID as a string.
        """
        return str(self.id)


class Model:
    """
    Represents an AI model in the system.

    Attributes:
        id (int): Unique identifier for the model.
        name (str): Name of the model.
        deployment_name (str): Deployment name of the model in Azure OpenAI.
        description (str): Description of the model.
        model_type (str): Type/category of the model.
        api_endpoint (str): API endpoint used to interact with the model.
        temperature (float): Sampling temperature for APIs like OpenAI (default 1.0).
        max_tokens (int): Maximum number of tokens allowed (default 32000).
        max_completion_tokens (int): Maximum number of completion tokens for the model.
        is_default (bool): Flag indicating if the model is the default one.
    """

    def __init__(
        self,
        id,
        name,
        deployment_name,
        description,
        model_type,
        api_endpoint,
        temperature=1.0,
        max_tokens=None,
        max_completion_tokens=500,
        is_default=False,
    ):
        """
        Initializes a Model instance.

        Args:
            id (int): Unique identifier for the model.
            name (str): Name of the model.
            deployment_name (str): Deployment name for Azure OpenAI models.
            description (str): Description of the model.
            model_type (str): Type of the model.
            api_endpoint (str): API endpoint for the model.
            temperature (float): Sampling temperature (default 1.0).
            max_tokens (int): Maximum number of tokens allowed (default 32000).
            max_completion_tokens (int): Maximum number of completion tokens.
            is_default (bool): Whether the model is the default one (default False).
        """
        self.id = id
        self.name = name
        self.deployment_name = deployment_name
        self.description = description
        self.model_type = model_type
        self.api_endpoint = api_endpoint
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_completion_tokens = max_completion_tokens
        self.is_default = is_default

    @staticmethod
    def get_default():
        """
        Fetches the default model from the database.

        Returns:
            Model: The default Model instance if found, otherwise None.
        """
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
            ValueError: If a required field is missing.
        """
        required_fields = ["name", "deployment_name", "api_endpoint"]
        for field in required_fields:
            if field not in config or not config[field]:
                raise ValueError(f"Missing required field: {field}")

    @staticmethod
    def get_all(limit=10, offset=0):
        """
        Retrieves all models with optional pagination.

        Args:
            limit (int): Number of models to retrieve (default is 10).
            offset (int): Offset for pagination (default is 0).

        Returns:
            list[Model]: List of Model instances.
        """
        db = get_db()
        models = db.execute(
            "SELECT * FROM models LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [Model(**dict(model)) for model in models]

    @staticmethod
    def get_by_id(model_id):
        """
        Fetches a model by its ID.

        Args:
            model_id (int): ID of the model to retrieve.

        Returns:
            Model: A Model instance if found, otherwise None.
        """
        db = get_db()
        model = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        if model:
            return Model(**dict(model))
        return None

    @staticmethod
    def create(
        name,
        deployment_name,
        description,
        model_type,
        api_endpoint,
        temperature,
        max_tokens,
        max_completion_tokens,
        is_default,
    ):
        """
        Creates a new model in the database.

        Args:
            name (str): Name of the model.
            deployment_name (str): Deployment name for Azure OpenAI models.
            description (str): Description of the model.
            model_type (str): Type of the model.
            api_endpoint (str): API endpoint for the model.
            temperature (float): Sampling temperature.
            max_tokens (int): Maximum number of tokens allowed.
            max_completion_tokens (int): Maximum number of completion tokens.
            is_default (bool): Whether this model is the default one.

        Returns:
            int: ID of the newly created model.
        """
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO models (name, deployment_name, description, model_type, api_endpoint, temperature, max_tokens, max_completion_tokens, is_default) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                deployment_name,
                description,
                model_type,
                api_endpoint,
                temperature,
                max_tokens,
                max_completion_tokens,
                is_default,
            ),
        )
        model_id = cursor.lastrowid
        db.commit()
        logger.info(f"Model created: {name}")
        return model_id

    @staticmethod
    def update(
        model_id,
        name,
        deployment_name,
        description,
        model_type,
        api_endpoint,
        temperature,
        max_tokens,
        max_completion_tokens,
        is_default,
    ):
        """
        Updates an existing model in the database.

        Args:
            model_id (int): ID of the model to update.
            name (str): Updated name of the model.
            deployment_name (str): Updated deployment name for Azure OpenAI.
            description (str): Updated description of the model.
            model_type (str): Updated type of the model.
            api_endpoint (str): Updated API endpoint.
            temperature (float): Updated sampling temperature.
            max_tokens (int): Updated maximum tokens.
            max_completion_tokens (int): Updated maximum completion tokens.
            is_default (bool): Updated default flag.
        """
        db = get_db()
        db.execute(
            "UPDATE models SET name = ?, deployment_name = ?, description = ?, model_type = ?, api_endpoint = ?, temperature = ?, max_tokens = ?, max_completion_tokens = ?, is_default = ? WHERE id = ?",
            (
                name,
                deployment_name,
                description,
                model_type,
                api_endpoint,
                temperature,
                max_tokens,
                max_completion_tokens,
                is_default,
                model_id,
            ),
        )
        db.commit()
        logger.info(f"Model updated: {name}")

    @staticmethod
    def delete(model_id):
        """
        Deletes a model from the database.

        Args:
            model_id (int): ID of the model to delete.
        """
        db = get_db()
        db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model deleted: {model_id}")

    @staticmethod
    def set_default(model_id):
        """
        Sets a specific model as the default model.

        Args:
            model_id (int): ID of the model to set as default.

        Note:
            Resets all other models' default flags.
        """
        db = get_db()
        db.execute("UPDATE models SET is_default = 0")
        db.execute("UPDATE models SET is_default = 1 WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model set as default: {model_id}")


class Chat:
    """
    Represents a chat session in the system.

    Attributes:
        id (int): Unique identifier for the chat.
        user_id (int): ID of the user associated with the chat.
        title (str): Title or name of the chat session.
        model_id (int, optional): ID of the model associated with the chat (if any).
    """

    def __init__(self, id, user_id, title, model_id=None):
        """
        Initializes a Chat instance.

        Args:
            id (int): Unique identifier for the chat.
            user_id (int): ID of the user owning this chat.
            title (str): Title of the chat.
            model_id (int, optional): ID of the model associated with this chat.
        """
        self.id = id
        self.user_id = user_id
        self.title = title
        self.model_id = model_id

    @staticmethod
    def get_model(chat_id):
        """
        Retrieves the ID of the model associated with a specific chat.

        Args:
            chat_id (int): ID of the chat.

        Returns:
            int: Model ID if found, otherwise None.
        """
        db = get_db()
        result = db.execute(
            "SELECT model_id FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
        return result["model_id"] if result else None

    @staticmethod
    def set_model(chat_id, model_id):
        """
        Associates a model with a specific chat.

        Args:
            chat_id (int): ID of the chat.
            model_id (int): ID of the model to associate with the chat.
        """
        db = get_db()
        db.execute("UPDATE chats SET model_id = ? WHERE id = ?", (model_id, chat_id))
        db.commit()
        logger.info(f"Model set for chat {chat_id}: {model_id}")

    @staticmethod
    def get_by_id(chat_id):
        """
        Retrieves a chat by its ID.

        Args:
            chat_id (int): ID of the chat to retrieve.

        Returns:
            Chat: A Chat instance if found, otherwise None.
        """
        db = get_db()
        chat = db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if chat:
            return Chat(
                chat["id"], chat["user_id"], chat["title"], chat.get("model_id")
            )
        return None

    @staticmethod
    def get_user_chats(user_id):
        """
        Retrieves all chats for a specific user.

        Args:
            user_id (int): ID of the user.

        Returns:
            list[dict]: A list of dictionaries representing chats.
        """
        db = get_db()
        chats = db.execute(
            "SELECT * FROM chats WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(chat) for chat in chats]

    @staticmethod
    def create(chat_id, user_id, title):
        """
        Creates a new chat in the database.

        Args:
            chat_id (int): Unique identifier for the chat.
            user_id (int): ID of the user who owns the chat.
            title (str): Title of the chat.
        """
        db = get_db()
        db.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, user_id, title),
        )
        db.commit()
        logger.info(f"Chat created: {chat_id} for user {user_id}")
