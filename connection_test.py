import os
import sys
from sqlalchemy import text
from database import get_db_state
from azure_search_client import AzureOpenAI

def test_connections():
    try:
        # Test DB
        engine = get_db_state().get("engine")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            print(f"Database connection OK: {result.scalar()}")

        # Test Azure OpenAI
        client = AzureOpenAI(os.getenv("AZURE_ENDPOINT"), os.getenv("AZURE_KEY"))
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Test"}]
        )
        print(f"Azure OpenAI connection OK")

    except Exception as e:
        print(f"CONNECTION FAILED: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    test_connections()
