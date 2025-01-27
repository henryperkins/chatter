#!/usr/bin/env python3
import sys
sys.path.append('.')

from database import db_session, init_db
from models.user import User

def make_admin(username: str):
    """Make the specified user an admin"""
    init_db()  # Ensure the database is initialized
    with db_session() as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            print(f"Error: User '{username}' not found")
            sys.exit(1)
        
        # Update the user's role to 'admin'
        user.role = 'admin'
        session.commit()
        print(f"Successfully made {username} an admin")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python make_admin.py <username>")
        sys.exit(1)
    
    make_admin(sys.argv[1])
