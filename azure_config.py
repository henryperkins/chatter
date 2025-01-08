# azure_config.py

import os
from openai import AzureOpenAI
import requests
import logging
from typing import Dict, Optional, Tuple, Any, Union

# Initialize logger
logger = logging.getLogger(__name__)


def validate_o1_preview_config(model_config: Dict[str, Any]) -> None:
    """Validate configuration for o1-preview models.

    Args:
        model_config (Dict[str, Any]): The model configuration dictionary.

    Raises:
        ValueError: If the configuration violates o1-preview requirements.
    """
    if not model_config.get("requires_o1_handling"):
        return

    messages = model_config.get("messages", [])
    if not messages:
        return

    # Check for system messages
    if any(
        msg.get("role") == "system"
        for msg in messages
    ):
        raise ValueError("o1-preview models do not support system messages")

    # Check other requirements
    if model_config.get("stream"):
        raise ValueError("o1-preview models do not support streaming")
    if model_config.get("max_tokens"):
        raise ValueError("o1-preview models use max_completion_tokens instead of max_tokens")
    if model_config.get("temperature") not in (None, 1, 1.0):
        raise ValueError("o1-preview models require temperature=1")


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
        "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
    )  # Updated to latest o1-preview version

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
            For o1-preview models (when requires_o1_handling is True):
            - API version must be in YYYY-MM-DD-preview format
            - System messages are not supported and will be filtered out
            - Streaming is not supported and will be disabled
            - Temperature must be 1
            - Uses max_completion_tokens instead of max_tokens

            Expected message structure:
            messages: list[dict[str, str]] containing:
            - role: "user" or "assistant" (no "system")
            - content: The message text

    Returns:
        Tuple[AzureOpenAI, str, Optional[float], Optional[int], int, bool]: The client, deployment name,
            temperature (or None), max_tokens, max_completion_tokens, and requires_o1_handling flag.

    Raises:
        ValueError: If required configuration parameters are missing or if o1-preview requirements
            are violated (see validate_o1_preview_config for specific validations).
    """
    # Get required fields, ensuring they exist
    api_endpoint = model_config.get("api_endpoint")
    api_key = model_config.get("api_key")
    deployment_name = model_config.get("deployment_name")
    
    # Validate required fields are present and not None
    if not api_endpoint or not api_key or not deployment_name:
        raise ValueError(
            "Missing required Azure OpenAI configuration. "
            "Please ensure api_endpoint, api_key, and deployment_name are set in the model configuration."
        )
    
    # Convert to strings only after validation
    api_endpoint = str(api_endpoint)
    api_key = str(api_key)
    deployment_name = str(deployment_name)
    api_version = str(model_config.get("api_version", "2024-02-15-preview"))
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

    # Validate required fields
    required_fields = {
        "api_endpoint": api_endpoint,
        "api_key": api_key,
        "api_version": api_version,
        "deployment_name": deployment_name,
        "max_completion_tokens": max_completion_tokens
    }

    # Ensure API version is correct for o1-preview
    if requires_o1_handling and api_version != "2024-12-01-preview":
        logger.warning("Updating API version to 2024-12-01-preview for o1-preview model")
        api_version = "2024-12-01-preview"

    for field_name, value in required_fields.items():
        if not value:
            raise ValueError(f"Missing required configuration parameter: {field_name}")

    if requires_o1_handling:
        # Enforce o1-preview specific requirements
        api_version = "2024-12-01-preview"  # Must use this specific version
        temperature = 1  # Temperature must be 1 for o1-preview
        max_tokens = None  # Use max_completion_tokens instead of max_tokens
        # Validate and update o1-preview configuration
        validate_o1_preview_config(model_config)

        # Filter out system messages if present
        messages = model_config.get("messages", [])
        if messages:
            model_config["messages"] = [
                msg for msg in messages
                if msg.get("role") != "system"
            ]
        if model_config.get("stream", False):
            # Disable streaming for o1-preview
            model_config["stream"] = False

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
        test_payload: Dict[str, Any] = {
            "messages": [{"role": "user", "content": "Test message"}],
            "max_completion_tokens": 1
        }

        # Configure payload for o1-preview models
        if api_version.endswith("-preview"):
            test_payload["temperature"] = 1.0  # Required for o1-preview
            test_payload.pop("max_tokens", None)  # Remove max_tokens if present
            # Filter out system messages
            messages = test_payload.get("messages", [])
            if messages:
                test_payload["messages"] = [
                    msg for msg in messages
                    if msg.get("role") != "system"
                ]

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
