#!/usr/bin/env python3
import sys
sys.path.append('.')

from database import get_db_state

def reset_database():
    """Reset the database to initial state"""
    db = get_db_state()
    
    print("WARNING: This will delete all data in the database!")
    response = input("Are you sure you want to continue? [y/N]: ")
    
    if response.lower() != 'y':
        print("Database reset cancelled")
        return
        
    db.drop_all()
    db.create_all()
    print("Database has been reset successfully")

if __name__ == "__main__":
    reset_database()
