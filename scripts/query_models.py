import sys
import os

# Add the application's root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db_session


def query_models():
    with db_session() as session:
        result = session.execute("SELECT id, api_key FROM models").fetchall()
        for row in result:
            print(f"ID: {row['id']}, API Key: {row['api_key']}")


if __name__ == "__main__":
    query_models()
