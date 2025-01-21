#!/usr/bin/env python3
import sys
sys.path.append('.')

from database import init_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.user import User
from models.model import Model

def reset_database():
    """Reset the database to initial state"""
    print("WARNING: This will delete all data in the database!")
    response = input("Are you sure you want to continue? [y/N]: ")
    
    if response.lower() != 'y':
        print("Database reset cancelled")
        return

    # Initialize fresh database
    init_db()
    print("Database has been reset successfully")

if __name__ == "__main__":
    reset_database()
