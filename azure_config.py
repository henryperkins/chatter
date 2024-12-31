# azure_config.py

import os
from dotenv import load_dotenv
import openai
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
        openai.api_type = "azure"
        openai.api_base = azure_endpoint
        openai.api_key = api_key
        openai.api_version = api_version
        _client = openai
        _deployment_name = deployment_name

    return _client, _deployment_name


def initialize_client_from_model(model_config):
    """Initialize and return the client using model configuration.

    Args:
        model_config (dict): The model configuration dictionary.

    Returns:
        Tuple[AzureOpenAI, str]: The Azure OpenAI client and deployment name.

    Raises:
        ValueError: If required fields are missing or if the model type is unsupported.
    """
    if not model_config:
        raise ValueError("Model configuration is required.")

    if model_config.get("model_type") != "azure":
        raise ValueError(f"Unsupported model type: {model_config.get('model_type')}")

    # Retrieve required configuration from the model config
    api_endpoint = model_config.get("api_endpoint")
    api_key = model_config.get("api_key")
    deployment_name = model_config.get(
        "name"
    )  # Assuming 'name' is used as the deployment name

    # Validate required configuration fields
    if not all([api_endpoint, api_key, deployment_name]):
        raise ValueError("Model configuration is missing required fields.")

    # Initialize the Azure OpenAI client
    client = AzureOpenAI(
        azure_endpoint=api_endpoint,
        api_key=api_key,
        api_version="2024-12-01-preview",  # Use default or specify as needed
    )

    return client, deployment_name
