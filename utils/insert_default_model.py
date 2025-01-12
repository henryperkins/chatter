import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def insert_default_model():
    """Insert or update the default model configuration in the database."""
    try:
        conn = sqlite3.connect('chat_app.db')
        cursor = conn.cursor()

        # First, check if the model exists
        cursor.execute("SELECT id FROM models WHERE deployment_name = 'o1-preview'")
        existing_model = cursor.fetchone()

        if existing_model:
            # Update existing model
            cursor.execute("""
                UPDATE models SET
                    name = 'Azure OpenAI o1-preview',
                    description = 'Azure OpenAI o1-preview model',
                    model_type = 'azure',
                    api_endpoint = 'https://openai-hp.openai.azure.com',
                    api_key = '9SPmgaBZ0tlnQrdRU0IxLsanKHZiEUMD2RASDEUhOchf6gyqRLWCJQQJ99BAACHYHv6XJ3w3AAABACOGKt5l',
                    temperature = 1.0,
                    max_completion_tokens = 500,
                    is_default = 1,
                    api_version = '2024-12-01-preview',
                    requires_o1_handling = 1
                WHERE deployment_name = 'o1-preview'
            """)
            logger.info("Existing model updated successfully")
        else:
            # Insert new model
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
                    api_version,
                    requires_o1_handling
                ) VALUES (
                    'Azure OpenAI o1-preview',
                    'o1-preview',
                    'Azure OpenAI o1-preview model',
                    'azure',
                    'https://openai-hp.openai.azure.com',
                    '9SPmgaBZ0tlnQrdRU0IxLsanKHZiEUMD2RASDEUhOchf6gyqRLWCJQQJ99BAACHYHv6XJ3w3AAABACOGKt5l',
                    1.0,
                    500,
                    1,
                    '2024-12-01-preview',
                    1
                )
            """)
            logger.info("New model inserted successfully")

        # Set all other models as non-default
        cursor.execute("""
            UPDATE models SET is_default = 0 
            WHERE deployment_name != 'o1-preview'
        """)

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    insert_default_model()
