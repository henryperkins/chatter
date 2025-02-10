import os
import sys

# Add the application's root directory to the Python path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Now we can import application modules
from app import create_app  # noqa: E402
from database import db_session  # noqa: E402
from sqlalchemy import text  # noqa: E402


def query_models():
    app = create_app()
    with app.app_context():
        with db_session() as session:
            result = session.execute(text("SELECT id, api_key FROM models")).mappings().fetchall()
            for row in result:
                print(f"ID: {row['id']}, API Key: {row['api_key']}")


if __name__ == "__main__":
    query_models()
