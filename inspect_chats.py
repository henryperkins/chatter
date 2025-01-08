import sqlite3

# Connect to the database
db_path = "chat_app.db"
connection = sqlite3.connect(db_path)

# Query to check the chat_id and user_id
chat_id = "e886b77f-5620-4a54-8fc1-977200d6729c"
user_id = 1

try:
    with connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id))
        result = cursor.fetchone()
        if result:
            print("Chat found:", result)
        else:
            print("No matching chat found for chat_id:", chat_id, "and user_id:", user_id)
finally:
    connection.close()
