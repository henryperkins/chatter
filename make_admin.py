from database import get_db

def make_admin(username):
    db = get_db()
    db.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
    db.commit()
    print(f"User '{username}' has been made an admin.")

if __name__ == "__main__":
    make_admin("hperkins")
