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
