#!/usr/bin/env python3
import sys
from datetime import datetime
from textwrap import dedent
from typing import List, Dict, Any
from flask import Flask

sys.path.append('.')

# Create a minimal Flask app
app = Flask(__name__)
app.config['DATABASE_URI'] = 'postgresql://username:password@localhost/dbname'  # Update with your actual DB URI

# Initialize database
from database import init_app
init_app(app)

def format_user(user: Dict[str, Any]) -> str:
    """Format user information for display"""
    created_at = user['created_at']
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    
    return dedent(f"""
        ID: {user['id']}
        Username: {user['username']}
        Email: {user['email']}
        Role: {user['role']}
        Created At: {created_at.strftime('%Y-%m-%d %H:%M:%S')}
        Verified: {user.get('is_verified', 'N/A')}
        Active: {user.get('is_active', 'N/A')}
    """).strip()

def list_users(show_password_hashes: bool = False) -> List[Dict[str, Any]]:
    """List all users in the database"""
    with app.app_context():
        from database import db_session
        with db_session() as db:
            # Select basic user info
            query = text("""
                SELECT id, username, email, role, created_at, is_verified, is_active
                FROM users
                ORDER BY created_at DESC
            """)
        
            if show_password_hashes:
                # Include password hashes if requested
                query = text("""
                    SELECT id, username, email, role, created_at, 
                           is_verified, is_active, password_hash
                    FROM users
                    ORDER BY created_at DESC
                """)
        
            users = db.execute(query).mappings().all()
            return users

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='List users in the database')
    parser.add_argument('--show-hashes', action='store_true',
                       help='Show password hashes (for verification only)')
    args = parser.parse_args()

    try:
        with app.app_context():
            users = list_users(show_password_hashes=args.show_hashes)
        
        if not users:
            print("No users found in the database")
            return

        print(f"Found {len(users)} users:\n")
        for user in users:
            print(format_user(user))
            if args.show_hashes:
                print(f"Password Hash: {user['password_hash']}")
            print("-" * 60)
            
    except Exception as e:
        print(f"Error listing users: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
