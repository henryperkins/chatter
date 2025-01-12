import sqlite3

# Connect to the database
db_path = "chat_app.db"
connection = sqlite3.connect(db_path)

# Data to insert
chat_id = "e886b77f-5620-4a54-8fc1-977200d6729c"
user_id = 1
title = "New Chat"

try:
    with connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, user_id, title),
        )
        print("Chat inserted successfully with chat_id:", chat_id)
finally:
    connection.close()
