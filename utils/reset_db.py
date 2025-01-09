import sqlite3
import os

# Remove existing database if it exists
if os.path.exists('chat_app.db'):
    os.remove('chat_app.db')

# Create new database and initialize schema
conn = sqlite3.connect('chat_app.db')
cursor = conn.cursor()

with open('schema.sql', 'r') as f:
    cursor.executescript(f.read())

conn.commit()
conn.close()

print("Database has been reset successfully!")