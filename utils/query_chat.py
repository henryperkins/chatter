from database import get_db
from app import app

def check_chat_exists(chat_id):
    with app.app_context():
        with get_db() as db:
            from sqlalchemy.sql import text
            result = db.execute(text("SELECT * FROM chats WHERE id = :chat_id"), {"chat_id": chat_id}).fetchall()
            if result:
                print(f"Chat ID {chat_id} exists in the database.")
            else:
                print(f"Chat ID {chat_id} does not exist in the database.")

if __name__ == "__main__":
    chat_id = "9a5818c3-03e7-4b52-851b-35b758af130d"
    check_chat_exists(chat_id)
