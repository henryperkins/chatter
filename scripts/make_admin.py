#!/usr/bin/env python3
import sys
sys.path.append('.')

from database import db_session
from models.user import User

def make_admin(username: str):
    """Make the specified user an admin"""
    with db_session() as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            print(f"Error: User '{username}' not found")
            sys.exit(1)
            
        user.is_admin = True
        session.commit()
        print(f"Successfully made {username} an admin")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/make_admin.py <username>")
        sys.exit(1)
    
    make_admin(sys.argv[1])
