#!/usr/bin/env python3
import sys
sys.path.append('.')

from database import db_session, init_app
from app import create_app
from models.user import User

def make_admin(username: str):
    """Make the specified user an admin"""
    app = create_app()  # Create Flask app instance
    with app.app_context():  # Use Flask app context
        with db_session(app) as session:
            # Use raw SQL to find the user by username
            result = session.execute(
                """
                SELECT id, username, email, password_hash, role, created_at, is_active
                FROM users
                WHERE LOWER(username) = LOWER(:username)
                """,
                {"username": username.strip()}
            ).mappings().first()

            if not result:
                print(f"Error: User '{username}' not found")
                sys.exit(1)

            # Update the user's role to 'admin'
            session.execute(
                """
                UPDATE users
                SET role = 'admin'
                WHERE id = :user_id
                """,
                {"user_id": result["id"]}
            )
            session.commit()
            print(f"Successfully made {username} an admin")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python make_admin.py <username>")
        sys.exit(1)
    
    make_admin(sys.argv[1])
