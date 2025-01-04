from database import get_db
from app import app  # Import the app object to set up the application context

def make_admin(username):
    with app.app_context():  # Set up the application context
        db = get_db()
        db.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
        db.commit()
        print(f"User '{username}' has been made an admin.")

if __name__ == "__main__":
    make_admin("hperkins")
