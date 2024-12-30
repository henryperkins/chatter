from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

class Chat:
    def __init__(self, id, user_id, title, context='', created_at=None):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.context = context
        self.created_at = created_at

    @staticmethod
    def get_context(chat_id):
        db = get_db()
        chat = db.execute(
            'SELECT context FROM chats WHERE id = ?', (chat_id,)
        ).fetchone()
        return chat['context'] if chat else ''

    @staticmethod
    def update_context(chat_id, context):
        db = get_db()
        db.execute(
            'UPDATE chats SET context = ? WHERE id = ?',
            (context, chat_id)
        )
        db.commit()

class Message:
    def __init__(self, id, chat_id, role, content, timestamp=None):
        self.id = id
        self.chat_id = chat_id
        self.role = role
        self.content = content
        self.timestamp = timestamp