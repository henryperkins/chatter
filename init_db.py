import sqlite3
from config import Config

def init_db():
    # Connect to the database (will create it if it doesn't exist)
    conn = sqlite3.connect('chat_app.db')
    cursor = conn.cursor()

    # Read and execute the schema
    with open('schema.sql', 'r') as f:
        cursor.executescript(f.read())

    # Initialize default model
    cursor.execute("""
        INSERT INTO models (
            name, deployment_name, description, model_type,
            api_endpoint, api_key, temperature, max_tokens,
            max_completion_tokens, is_default, requires_o1_handling,
            supports_streaming, api_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        Config.DEFAULT_MODEL_NAME,
        Config.DEFAULT_DEPLOYMENT_NAME,
        Config.DEFAULT_MODEL_DESCRIPTION,
        "azure",  # Default model type
        Config.DEFAULT_API_ENDPOINT,
        Config.AZURE_API_KEY,
        Config.DEFAULT_TEMPERATURE,
        Config.DEFAULT_MAX_TOKENS,
        Config.DEFAULT_MAX_COMPLETION_TOKENS,
        True,  # is_default
        Config.DEFAULT_REQUIRES_O1_HANDLING,
        Config.DEFAULT_SUPPORTS_STREAMING,
        Config.DEFAULT_API_VERSION
    ))

    # Commit changes and close connection
    conn.commit()
    conn.close()

    print("Database initialized successfully with default o1-preview model!")


if __name__ == '__main__':
    init_db()
