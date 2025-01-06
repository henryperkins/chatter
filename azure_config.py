# azure_config.py

import os
from openai import AzureOpenAI
import requests
import logging
from typing import Dict, Optional, Tuple, Any, Union, List

# Initialize logger
logger = logging.getLogger(__name__)

def get_azure_client(deployment_name: Optional[str] = None) -> Tuple[AzureOpenAI, str]:
    """Retrieve the Azure OpenAI client and deployment name.

    Args:
        deployment_name (str, optional): The name of the deployment to use. If not provided,
            the default deployment (from environment variables) will be used.

    Returns:
        Tuple[AzureOpenAI, str]: The client and deployment name.

    Raises:
        ValueError: If required environment variables are missing.
    """
    # If no deployment name is provided, use the default from environment variables
    if not deployment_name:
        deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        if not deployment_name:
            raise ValueError(
                "Default deployment name not found in environment variables."
            )

    # Retrieve Azure OpenAI configuration from environment variables
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_KEY")
    api_version = os.getenv(
        "AZURE_OPENAI_API_VERSION", "2023-10-01-preview"
    )  # Use a valid current API version

    # Validate required configuration variables
    if not all([azure_endpoint, api_key, deployment_name]):
        raise ValueError(
            "Missing required Azure OpenAI environment variables. "
            "Please set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, and AZURE_OPENAI_DEPLOYMENT_NAME."
        )

    # Validate azure_endpoint is not None
    if not azure_endpoint:
        raise ValueError("Azure endpoint cannot be None")

    # Configure the OpenAI client for Azure
    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=str(azure_endpoint),  # Ensure string type
        api_version=api_version,
    )

    return client, deployment_name

def initialize_client_from_model(
    model_config: Dict[str, Any]
) -> Tuple[AzureOpenAI, str, Optional[float], Optional[int], int, bool]:
    """Initialize Azure OpenAI client from model configuration.

    Args:
        model_config (Dict[str, Any]): A dictionary containing model attributes.

    Returns:
        Tuple[AzureOpenAI, str, Optional[float], Optional[int], int, bool]: The client, deployment name,
            temperature (or None), max_tokens, max_completion_tokens, and requires_o1_handling flag.

    Raises:
        ValueError: If required configuration parameters are missing.
    """
    api_endpoint: str = str(model_config.get("api_endpoint"))
    api_key: str = str(model_config.get("api_key"))
    api_version: str = str(model_config.get("api_version", "2023-10-01-preview"))  # Updated to valid version
    deployment_name: str = str(model_config.get("deployment_name"))
    temperature: Optional[float] = (
        float(model_config.get("temperature", 0.7))
        if model_config.get("temperature") is not None
        else None
    )
    max_tokens: Optional[int] = None
    if model_config.get("max_tokens") is not None:
        try:
            max_tokens = int(str(model_config.get("max_tokens")))
        except (ValueError, TypeError):
            raise ValueError("max_tokens must be a valid integer or None")
    max_completion_tokens: int = int(model_config.get("max_completion_tokens", 500))
    requires_o1_handling: bool = bool(model_config.get("requires_o1_handling", False))

    # Validate required fields with type annotations
    required_fields: Dict[str, Union[str, int]] = {
        "api_endpoint": api_endpoint,
        "api_key": api_key,
        "api_version": api_version,
        "deployment_name": deployment_name,
        "max_completion_tokens": max_completion_tokens,
    }

    for field_name, value in required_fields.items():
        if not value:
            raise ValueError(f"Missing required configuration parameter: {field_name}")

    if requires_o1_handling:
        # Enforce o1-preview specific requirements
        if api_version != "2023-10-01-preview":
            api_version = "2023-10-01-preview"  # Override to correct version
        temperature = 1  # Set temperature to 1 as required
        max_tokens = None  # max_tokens is not used for o1-preview models

    # Initialize the Azure OpenAI client
    client = AzureOpenAI(
        azure_endpoint=api_endpoint, api_key=api_key, api_version=api_version
    )

    return (
        client,
        deployment_name,
        temperature,
        max_tokens,
        max_completion_tokens,
        requires_o1_handling,
    )

def validate_api_endpoint(
    api_endpoint: str, api_key: str, deployment_name: str, api_version: str
) -> bool:
    """Validate the API endpoint, deployment name, and key by making a test request.

    Args:
        api_endpoint (str): The base API endpoint URL (e.g., https://<instance_name>.openai.azure.com).
        api_key (str): The API key.
        deployment_name (str): The deployment name for the model.
        api_version (str): The API version (e.g., 2023-10-01-preview).

    Returns:
        bool: True if the endpoint, deployment name, and key are valid, False otherwise.
    """
    try:
        # Construct the full URL for validation
        test_url = (
            f"{api_endpoint.rstrip('/')}/openai/deployments/"
            f"{deployment_name}/chat/completions?api-version={api_version}"
        )
        logger.debug("Validating API endpoint and deployment.")

        # Prepare the test request payload with type annotations
        test_payload: Dict[str, Union[List[Dict[str, str]], int]] = {
            "messages": [{"role": "user", "content": "Test message"}],
            "max_completion_tokens": 1,
        }

        # Exclude unnecessary parameters for o1-preview models
        if api_version == "2023-10-01-preview":
            test_payload.pop("temperature", None)  # Ensure temperature is not included

        # Make a test request to the API
        response = requests.post(
            test_url,
            headers={"api-key": api_key},
            json=test_payload,
            timeout=5,
        )

        logger.debug(f"Validation response status code: {response.status_code}")

        # Return True if the response status code indicates success
        return response.status_code == 200
    except Exception as e:
        logger.error(f"API endpoint validation failed: {str(e)}")
        return False
