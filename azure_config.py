# azure_config.py

import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# Private client instance and deployment name
_client = None
_deployment_name = None


def get_azure_client():
    """Retrieve the Azure OpenAI client and deployment name.

    This function initializes the client if it hasn't been already,
    using environment variables for configuration.
    """
    global _client, _deployment_name

    if _client is None or _deployment_name is None:
        # Retrieve Azure OpenAI configuration from environment variables
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

        # Validate required configuration variables
        if not all([azure_endpoint, api_key, deployment_name]):
            raise ValueError(
                "Missing required Azure OpenAI environment variables. "
                "Please set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, and AZURE_OPENAI_DEPLOYMENT_NAME."
            )

        # Configure the OpenAI client for Azure
        _client = AzureOpenAI(
            api_key=api_key, azure_endpoint=azure_endpoint, api_version=api_version
        )
        _deployment_name = deployment_name

    return _client, _deployment_name


def initialize_client_from_model(model_config):
    """Initialize and return the client using model configuration.

    Args:
        model_config (dict): The model configuration dictionary.

    Returns:
        Tuple[AzureOpenAI, str, float, int]: The Azure OpenAI client, deployment name, temperature, and max_tokens.

    Raises:
        ValueError: If required fields are missing or if the model type is unsupported.
    """
    if not model_config:
        raise ValueError("Model configuration is required.")

    if model_config.get("model_type") != "azure":
        raise ValueError(f"Unsupported model type: {model_config.get('model_type')}")

    # Retrieve required configuration from the model config
    api_endpoint = model_config.get("api_endpoint")
    deployment_name = model_config.get("deployment_name")
    api_version = model_config.get("api_version", "2024-12-01-preview")
    temperature = model_config.get("temperature", 1.0)
    max_tokens = model_config.get("max_tokens")
    max_completion_tokens = model_config.get("max_completion_tokens")

    # Handle o1-preview specific requirements
    if "o1-preview" in deployment_name:
        api_version = "2024-12-01-preview"
        temperature = 1
        max_tokens = None  # max_tokens is not used for o1-preview

    # Validate required configuration fields
    if not all([api_endpoint, deployment_name]):
        raise ValueError("Model configuration is missing required fields.")

    # Retrieve API key from environment variable
    api_key = os.getenv("AZURE_OPENAI_KEY")
    if not api_key:
        raise ValueError("AZURE_OPENAI_KEY environment variable not set.")

    # Initialize the Azure OpenAI client
    client = AzureOpenAI(
        azure_endpoint=api_endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    return client, deployment_name, temperature, max_tokens, max_completion_tokens
