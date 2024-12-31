import sqlite3
from database import get_db
import logging

logger = logging.getLogger(__name__)

class User:
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

    @staticmethod
    def get_by_id(user_id):
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user:
            return User(user['id'], user['username'], user['email'])
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

class Model:
    @staticmethod
    def get_all(limit=10, offset=0):
        db = get_db()
        models = db.execute(
            "SELECT * FROM models LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [Model(**dict(model)) for model in models]

    @staticmethod
    def get_by_id(model_id):
        db = get_db()
        model = db.execute(
            "SELECT * FROM models WHERE id = ?", (model_id,)
        ).fetchone()
        if model:
            return Model(**dict(model))
        return None

    @staticmethod
    def validate_model_config(config):
        required_fields = ['name', 'api_endpoint', 'api_key']
        for field in required_fields:
            if field not in config or not config[field]:
                raise ValueError(f"Missing required field: {field}")

    @staticmethod
    def create(name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default):
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO models (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default)
        )
        model_id = cursor.lastrowid
        db.commit()
        logger.info(f"Model created: {name}")
        return model_id

    @staticmethod
    def update(model_id, name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default):
        db = get_db()
        db.execute(
            "UPDATE models SET name = ?, description = ?, model_type = ?, api_endpoint = ?, api_key = ?, temperature = ?, max_tokens = ?, is_default = ? WHERE id = ?",
            (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default, model_id)
        )
        db.commit()
        logger.info(f"Model updated: {name}")

    @staticmethod
    def delete(model_id):
        db = get_db()
        db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model deleted: {model_id}")

    @staticmethod
    def set_default(model_id):
        db = get_db()
        db.execute("UPDATE models SET is_default = 0")
        db.execute("UPDATE models SET is_default = 1 WHERE id = ?", (model_id,))
        db.commit()
        logger.info(f"Model set as default: {model_id}")

class Chat:
    @staticmethod
    def get_all(user_id):
        db = get_db()
        chats = db.execute(
            "SELECT * FROM chats WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [Chat(**dict(chat)) for chat in chats]

    @staticmethod
    def get_by_id(chat_id):
        db = get_db()
        chat = db.execute(
            "SELECT * FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
        if chat:
            return Chat(**dict(chat))
        return None

    @staticmethod
    def get_user_chats(user_id):
        db = get_db()
        chats = db.execute(
            "SELECT id, title FROM chats WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [{"id": chat['id'], "title": chat['title']} for chat in chats]

    @staticmethod
    def create(chat_id, user_id, title):
        db = get_db()
        db.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, user_id, title)
        )
        db.commit()
        logger.info(f"Chat created: {chat_id} for user {user_id}")

    @staticmethod
    def get_context(chat_id):
        db = get_db()
        context = db.execute(
            "SELECT context FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
        return context['context'] if context else ""

    @staticmethod
    def update_context(chat_id, context):
        db = get_db()
        db.execute(
            "UPDATE chats SET context = ? WHERE id = ?",
            (context, chat_id)
        )
        db.commit()
        logger.info(f"Context updated for chat {chat_id}")
