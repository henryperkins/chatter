#!/usr/bin/env python3
import sys
import os
sys.path.append('.')

from database import init_db

def reset_database():
    """Reset the database to initial state"""
    print("WARNING: This will delete all data in the database!")
    response = input("Are you sure you want to continue? [y/N]: ")
    
    if response.lower() not in ['y', 'yes']:
        print("Database reset cancelled")
        return

    # Get database URI from environment or use default
    db_uri = os.getenv('DATABASE_URI', 'sqlite:///instance/chatter.db')
    
    # Initialize fresh database
    try:
        init_db(db_uri)
        print("Database has been reset successfully")
    except Exception as e:
        print(f"Error resetting database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    reset_database()
