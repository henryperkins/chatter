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
    AZURE_API_KEY = os.getenv("AZURE_API_KEY", "9SPmgaBZ0tlnQrdRU0IxLsanKHZiEUMD2RASDEUhOchf6gyqRLWCJQQJ99BAACHYHv6XJ3w3AAABACOGKt5l")
    DEFAULT_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    DEFAULT_API_ENDPOINT = os.getenv(
        "DEFAULT_API_ENDPOINT", "https://openai-hp.openai.azure.com/"
    )
    DEFAULT_DEPLOYMENT_NAME = os.getenv("DEFAULT_DEPLOYMENT_NAME", "o1-preview")
    DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "o1-preview")
    DEFAULT_MODEL_DESCRIPTION = os.getenv(
        "DEFAULT_MODEL_DESCRIPTION", "Azure OpenAI o1-preview model"
    )
    DEFAULT_MODEL_TYPE = os.getenv("DEFAULT_MODEL_TYPE", "o1-preview")
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))  # o1-preview requires exactly 1.0
    DEFAULT_MAX_TOKENS = None  # o1-preview doesn't use max_tokens
    DEFAULT_MAX_COMPLETION_TOKENS = int(
        os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "8300")  # o1-preview can handle up to 8300 tokens
    )
    DEFAULT_REQUIRES_O1_HANDLING = True  # Enable o1-preview specific handling
    DEFAULT_SUPPORTS_STREAMING = False  # o1-preview doesn't support streaming
    
    # Default model configuration
    DEFAULT_MODEL_CONFIG = {
        "name": DEFAULT_MODEL_NAME,
        "deployment_name": DEFAULT_DEPLOYMENT_NAME,
        "description": DEFAULT_MODEL_DESCRIPTION,
        "model_type": DEFAULT_MODEL_TYPE,
        "api_endpoint": DEFAULT_API_ENDPOINT,
        "api_key": AZURE_API_KEY,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "max_completion_tokens": DEFAULT_MAX_COMPLETION_TOKENS,
        "api_version": DEFAULT_API_VERSION,
        "is_default": True,
        "requires_o1_handling": DEFAULT_REQUIRES_O1_HANDLING,
        "supports_streaming": DEFAULT_SUPPORTS_STREAMING
    }

    # Other configuration variables can be added here
