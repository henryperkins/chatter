# azure_config.py

import os
from dotenv import load_dotenv
from openai import AzureOpenAI
import requests

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
        api_version = os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
        )  # Default to o1-preview
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
    """Initialize Azure OpenAI client from model configuration."""
    api_endpoint = model_config.get("api_endpoint")
    api_key = model_config.get("api_key")
    api_version = model_config.get("api_version")
    deployment_name = model_config.get("deployment_name")
    temperature = model_config.get("temperature", 0.7)
    max_tokens = model_config.get("max_tokens")
    max_completion_tokens = model_config.get("max_completion_tokens")
    requires_o1_handling = model_config.get("requires_o1_handling", False)

    if not all([api_endpoint, api_key, api_version, deployment_name]):
        raise ValueError("Missing required configuration parameters")

    if requires_o1_handling:
        # Enforce o1-preview specific requirements
        api_version = "2024-12-01-preview"
        temperature = 1  # Fixed temperature for o1-preview models
        max_tokens = None  # max_tokens is not used for o1-preview models

        if not max_completion_tokens:
            raise ValueError("max_completion_tokens is required for models requiring o1 handling")

    # Initialize the Azure OpenAI client
    client = AzureOpenAI(
        azure_endpoint=api_endpoint,
        api_key=api_key,
        api_version=api_version
    )

    return client, deployment_name, temperature, max_tokens, max_completion_tokens


def validate_api_endpoint(api_endpoint, api_key):
    """Validate the API endpoint and key by making a test request.

    Args:
        api_endpoint (str): The API endpoint URL.
        api_key (str): The API key.

    Returns:
        bool: True if the endpoint and key are valid, False otherwise.
    """
    try:
        response = requests.get(
            api_endpoint, headers={"Authorization": f"Bearer {api_key}"}, timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"API endpoint validation failed: {str(e)}")
        return False
