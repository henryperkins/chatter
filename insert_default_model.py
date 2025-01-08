import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def insert_default_model():
    """Insert a default model configuration into the database."""
    try:
        conn = sqlite3.connect('chat_app.db')
        cursor = conn.cursor()

        # Check if a default model already exists
        cursor.execute("SELECT COUNT(*) FROM models WHERE is_default = 1")
        if cursor.fetchone()[0] > 0:
            logger.info("Default model already exists")
            return

        # Insert a placeholder default model
        cursor.execute("""
            INSERT INTO models (
                name,
                deployment_name,
                description,
                model_type,
                api_endpoint,
                api_key,
                temperature,
                max_completion_tokens,
                is_default,
                api_version
            ) VALUES (
                'Default Azure Model',
                'gpt-4',
                'Default Azure OpenAI model configuration',
                'azure',
                'https://your-resource.openai.azure.com',
                'your-api-key',
                0.7,
                500,
                1,
                '2024-02-15-preview'
            )
        """)

        conn.commit()
        logger.info("Default model inserted successfully")

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    insert_default_model()
