# config.py

import os


class Config:
    # Database configuration
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///chat_app.db")
    # Ensure that ENCRYPTION_KEY is set securely and kept secret
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")  # e.g., os.environ['ENCRYPTION_KEY']
    # Secret key for Flask sessions
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")

    # Azure OpenAI configuration
    AZURE_API_KEY = os.getenv("AZURE_API_KEY")
    DEFAULT_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    DEFAULT_API_ENDPOINT = os.getenv(
        "DEFAULT_API_ENDPOINT", "https://your-resource.openai.azure.com"
    )
    DEFAULT_DEPLOYMENT_NAME = os.getenv("DEFAULT_DEPLOYMENT_NAME", "gpt-4")
    DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "GPT-4")
    DEFAULT_MODEL_DESCRIPTION = os.getenv(
        "DEFAULT_MODEL_DESCRIPTION", "Default GPT-4 model"
    )
    DEFAULT_MODEL_TYPE = os.getenv("DEFAULT_MODEL_TYPE", "azure")
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
    DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "4000"))
    DEFAULT_MAX_COMPLETION_TOKENS = int(
        os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "500")
    )
    DEFAULT_REQUIRES_O1_HANDLING = (
        os.getenv("DEFAULT_REQUIRES_O1_HANDLING", "False").lower() == "true"
    )
    DEFAULT_SUPPORTS_STREAMING = (
        os.getenv("DEFAULT_SUPPORTS_STREAMING", "True").lower() == "true"
    )

    # Other configuration variables can be added here
