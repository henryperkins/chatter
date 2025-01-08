import sqlite3
import argparse

def inspect_models():
    """Display all model configurations in the database."""
    connection = sqlite3.connect("chat_app.db")
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, name, deployment_name, model_type, api_endpoint, api_key,
                   temperature, max_tokens, max_completion_tokens, is_default, api_version
            FROM models
        """)
        models = cursor.fetchall()
        if models:
            print("\nModel Configurations:")
            print("-" * 80)
            for model in models:
                print(f"ID: {model[0]}")
                print(f"Name: {model[1]}")
                print(f"Deployment: {model[2]}")
                print(f"Type: {model[3]}")
                print(f"API Endpoint: {model[4]}")
                print(f"API Key: {'*' * 8}{model[5][-4:] if model[5] else 'Not Set'}")
                print(f"Temperature: {model[6]}")
                print(f"Max Tokens: {model[7]}")
                print(f"Max Completion Tokens: {model[8]}")
                print(f"Is Default: {bool(model[9])}")
                print(f"API Version: {model[10]}")
                print("-" * 80)
        else:
            print("No models found in the database")
    finally:
        connection.close()

def inspect_chats():
    """Display all chats in the database."""
    connection = sqlite3.connect("chat_app.db")
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM chats")
        chats = cursor.fetchall()
        if chats:
            print("\nChats:")
            print("-" * 80)
            for chat in chats:
                print(f"Chat ID: {chat[0]}")
                print(f"User ID: {chat[1]}")
                print(f"Title: {chat[2]}")
                print(f"Model ID: {chat[3]}")
                print(f"Created: {chat[4]}")
                print("-" * 80)
        else:
            print("No chats found in the database")
    finally:
        connection.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect database contents")
    parser.add_argument("--models", action="store_true", help="Show model configurations")
    parser.add_argument("--chats", action="store_true", help="Show chats")
    args = parser.parse_args()

    if args.models:
        inspect_models()
    if args.chats:
        inspect_chats()
    if not (args.models or args.chats):
        print("Please specify what to inspect: --models and/or --chats")
