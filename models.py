# models.py

from flask_login import UserMixin
from database import get_db
import logging

logger = logging.getLogger(__name__)


class User(UserMixin):
    """User model compatible with Flask-Login."""

    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

    @staticmethod
    def get_by_id(user_id):
        """Retrieve a user by ID."""
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user:
            return User(user["id"], user["username"], user["email"])
        return None

    @staticmethod
    def get_by_username(username):
        """Retrieve a user by username."""
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if user:
            return User(user["id"], user["username"], user["email"])
        return None

    @staticmethod
    def create(username, email, password_hash):
        """Create a new user."""
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash),
            )
            db.commit()
            logger.info(f"User created: {username}")
            return True
        except Exception as e:
            logger.error(f"Error creating user {username}: {str(e)}")
            return False

    @staticmethod
    def validate_credentials(username, password_hash):
        """Validate user credentials."""
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND password_hash = ?",
            (username, password_hash),
        ).fetchone()
        if user:
            return User(user["id"], user["username"], user["email"])
        return None


class Chat:
    """Chat model representing a conversation."""

    def __init__(self, id, user_id, title, context="", created_at=None):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.context = context
        self.created_at = created_at

    @staticmethod
    def get_by_id(chat_id):
        """Retrieve a chat by ID."""
        db = get_db()
        chat = db.execute(
            "SELECT * FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if chat:
            return Chat(
                chat["id"],
                chat["user_id"],
                chat["title"],
                chat["context"],
                chat["created_at"],
            )
        return None

    @staticmethod
    def create(chat_id, user_id, title):
        """Create a new chat."""
        db = get_db()
        db.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, user_id, title),
        )
        db.commit()
        logger.info(f"Chat created: {chat_id} for user {user_id}")

    @staticmethod
    def get_user_chats(user_id):
        """Retrieve all chats for a given user."""
        db = get_db()
        chats = db.execute(
            "SELECT id, title, created_at FROM chats WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(chat) for chat in chats]

    @staticmethod
    def update_title(chat_id, title):
        """Update the title of a chat."""
        db = get_db()
        db.execute(
            "UPDATE chats SET title = ? WHERE id = ?",
            (title, chat_id),
        )
        db.commit()
        logger.info(f"Chat {chat_id} title updated to {title}")

    @staticmethod
    def delete(chat_id):
        """Delete a chat and its messages."""
        db = get_db()
        db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        db.commit()
        logger.info(f"Chat {chat_id} and associated messages deleted")

    @staticmethod
    def get_context(chat_id):
        """Retrieve the context of a chat."""
        db = get_db()
        chat = db.execute(
            "SELECT context FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        return chat["context"] if chat else ""

    @staticmethod
    def update_context(chat_id, context):
        """Update the context of a chat."""
        db = get_db()
        db.execute("UPDATE chats SET context = ? WHERE id = ?", (context, chat_id))
        db.commit()
        logger.info(f"Chat {chat_id} context updated")


class Message:
    """Message model representing a chat message."""

    def __init__(self, id, chat_id, role, content, timestamp=None):
        self.id = id
        self.chat_id = chat_id
        self.role = role
        self.content = content
        self.timestamp = timestamp

    @staticmethod
    def add_message(chat_id, role, content):
        """Add a message to a chat."""
        db = get_db()
        db.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        db.commit()
        logger.debug(f"Added message to chat {chat_id}: {role}: {content[:50]}...")

    @staticmethod
    def get_messages(chat_id):
        """Retrieve all messages for a chat."""
        db = get_db()
        messages = db.execute(
            "SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp",
            (chat_id,),
        ).fetchall()
        return [dict(msg) for msg in messages]

    @staticmethod
    def delete_messages(chat_id):
        """Delete all messages for a chat."""
        db = get_db()
        db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        db.commit()
        logger.info(f"All messages deleted for chat {chat_id}")


class Model:
    """Model class for managing AI models."""

    def __init__(self, id, name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default, created_at):
        self.id = id
        self.name = name
        self.description = description
        self.model_type = model_type
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.is_default = is_default
        self.created_at = created_at

    @staticmethod
    def get_all():
        """Retrieve all models from the database."""
        db = get_db()
        models = db.execute("SELECT * FROM models").fetchall()
        return [Model(**dict(model)) for model in models]

    @staticmethod
    def get_by_id(model_id):
        """Retrieve a model by ID."""
        db = get_db()
        model = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        if model:
            return Model(**dict(model))
        return None

    @staticmethod
    def create(name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default):
        """Create a new model."""
        db = get_db()
        db.execute(
            "INSERT INTO models (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default),
        )
        db.commit()
        logger.info(f"Model created: {name}")
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]

    @staticmethod
    def update(model_id, name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default):
        """Update an existing model."""
        db = get_db()
        db.execute(
            "UPDATE models SET name = ?, description = ?, model_type = ?, api_endpoint = ?, api_key = ?, temperature = ?, max_tokens = ?, is_default = ? WHERE id = ?",
            (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default, model_id),
        )
        db.commit()
        logger.info(f"Model updated: {name}")

    @staticmethod
    def delete(model_id):
        """Delete a model."""
        db = get_db()
        db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model deleted: {model_id}")

    @staticmethod
    def set_default(model_id):
        """Set a model as the default."""
        db = get_db()
        db.execute("UPDATE models SET is_default = 0")
        db.execute("UPDATE models SET is_default = 1 WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model set as default: {model_id}")
