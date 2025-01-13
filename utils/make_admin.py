import sys
import os
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import get_db  
from app import app  # Import the app object to set up the application context

def make_admin(username):
    with app.app_context():  # Set up the application context
        db = get_db()
        db.execute(
            text("UPDATE users SET role = 'admin' WHERE username = :username"),
            {"username": username}
        )
        db.commit()
        print(f"User '{username}' has been made an admin.")


if __name__ == "__main__":
    make_admin("hperkins")
