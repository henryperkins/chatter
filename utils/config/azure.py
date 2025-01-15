from openai import AzureOpenAI
import requests
import logging
from typing import Dict, Optional, Tuple, Any
from utils.config import Config

# Initialize logger
logger = logging.getLogger(__name__)

def validate_o1_preview_config(model_config: Dict[str, Any]) -> None:
    """
    Validate configuration for o1-preview models.

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
    if any(msg.get("role") == "system" for msg in messages):
        raise ValueError("o1-preview models do not support system messages")

    # Check other requirements
    if model_config.get("stream"):
        raise ValueError("o1-preview models do not support streaming")
    if model_config.get("max_tokens"):
        raise ValueError(
            "o1-preview models use max_completion_tokens instead of max_tokens"
        )
    if model_config.get("temperature") not in (None, 1, 1.0):
        raise ValueError("o1-preview models require temperature=1")

def get_azure_client(deployment_name: Optional[str] = None) -> Tuple[AzureOpenAI, str]:
    """
    Retrieve the Azure OpenAI client and deployment name.

    Args:
        deployment_name (Optional[str]): The name of the deployment to use. If not provided,
                                      the default deployment (from centralized configuration)
                                      will be used.

    Returns:
        Tuple[AzureOpenAI, str]: The client and deployment name.

    Raises:
        ValueError: If required configuration variables are missing.
    """
    # Use deployment name from configuration if not provided
    if not deployment_name:
        deployment_name = Config.AZURE_DEPLOYMENT_NAME
    if not deployment_name:
        raise ValueError("Default deployment name not found in configuration.")

    # Retrieve Azure OpenAI configuration from centralized config
    azure_endpoint = Config.AZURE_API_ENDPOINT
    api_key = Config.AZURE_API_KEY
    api_version = Config.AZURE_API_VERSION

    # Validate required configuration variables
    if not all([azure_endpoint, api_key, deployment_name]):
        raise ValueError(
            "Missing required Azure OpenAI configuration variables. "
            "Please ensure AZURE_API_ENDPOINT, AZURE_API_KEY, and AZURE_DEPLOYMENT_NAME are set."
        )

    # Configure the OpenAI client for Azure
    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=str(azure_endpoint),  # Ensure string type
        api_version=api_version,
    )

    return client, deployment_name

def initialize_client_from_model(
    model_config: Dict[str, Any],
    timeout_seconds: int = 30,  # Add timeout_seconds parameter with default value
) -> Tuple[AzureOpenAI, str, Optional[float], Optional[int], int, bool]:
    """
    Initialize Azure OpenAI client from model configuration.

    Args:
        model_config (Dict[str, Any]): A dictionary containing model attributes.
            For o1-preview models (when requires_o1_handling is True):
            - API version must be in YYYY-MM-DD-preview format
            - System messages are not supported and will be filtered out
            - Streaming is not supported and will be disabled
            - Temperature must be 1
            - Uses max_completion_tokens instead of max_tokens

    Returns:
        Tuple[AzureOpenAI, str, Optional[float], Optional[int], int, bool]:
            The client, deployment name, temperature, max_tokens,
            max_completion_tokens, and requires_o1_handling flag.

    Raises:
        ValueError: If required configuration parameters are missing or if o1-preview requirements
                    are violated (see validate_o1_preview_config for specific validations).
    """
    # Get required fields, falling back to centralized configuration
    api_endpoint = model_config.get("api_endpoint") or Config.AZURE_API_ENDPOINT
    api_key = model_config.get("api_key") or Config.AZURE_API_KEY
    deployment_name = (
        model_config.get("deployment_name") or Config.AZURE_DEPLOYMENT_NAME
    )
    api_version = model_config.get("api_version") or Config.AZURE_API_VERSION
    temperature: Optional[float] = model_config.get(
        "temperature", Config.DEFAULT_TEMPERATURE
    )
    max_tokens: Optional[int] = model_config.get(
        "max_tokens", Config.DEFAULT_MAX_TOKENS
    )
    max_completion_tokens: int = model_config.get(
        "max_completion_tokens", Config.DEFAULT_MAX_COMPLETION_TOKENS
    )
    requires_o1_handling: bool = model_config.get(
        "requires_o1_handling", Config.DEFAULT_REQUIRES_O1_HANDLING
    )

    # Validate required fields
    required_fields = {
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
        api_version = Config.AZURE_API_VERSION  # Must use this specific version
        temperature = Config.DEFAULT_TEMPERATURE  # Temperature must be 1 for o1-preview
        max_tokens = None  # Use max_completion_tokens instead of max_tokens

        # Validate and update o1-preview configuration
        validate_o1_preview_config(model_config)

        # Filter out system messages if present
        if messages := model_config.get("messages", []):
            model_config["messages"] = [
                msg for msg in messages if msg.get("role") != "system"
            ]
        if model_config.get("stream", False):
            # Disable streaming for o1-preview
            model_config["stream"] = False

    # Initialize the Azure OpenAI client with the provided timeout
    client = AzureOpenAI(
        azure_endpoint=api_endpoint,
        api_key=api_key,
        api_version=api_version,
        timeout=timeout_seconds,  # Use the passed timeout_seconds parameter
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
    api_endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    deployment_name: Optional[str] = None,
    api_version: Optional[str] = None,
) -> bool:
    """
    Validate the API endpoint, deployment name, and key by making a test request.

    Args:
        api_endpoint (Optional[str]): The base API endpoint URL.
        api_key (Optional[str]): The API key.
        deployment_name (Optional[str]): The deployment name for the model.
        api_version (Optional[str]): The API version.

    Returns:
        bool: True if the endpoint, deployment name, and key are valid, False otherwise.

    Raises:
        ValueError: If the API endpoint URL is invalid.
        Exception: If there's an unexpected error during validation.
    """
    # Use centralized configuration if arguments are not provided
    api_endpoint = api_endpoint or Config.AZURE_API_ENDPOINT
    api_key = api_key or Config.AZURE_API_KEY
    deployment_name = deployment_name or Config.AZURE_DEPLOYMENT_NAME
    api_version = api_version or Config.AZURE_API_VERSION

    try:
        def construct_test_url(
            api_endpoint: str, deployment_name: str, api_version: str
        ) -> str:
            """
            Construct the full URL for validation.

            Args:
                api_endpoint (str): The base API endpoint URL.
                deployment_name (str): The deployment name for the model.
                api_version (str): The API version.

            Returns:
                str: The constructed URL.
            """
            return (
                f"{api_endpoint.rstrip('/')}/openai/deployments/"
                f"{deployment_name}/chat/completions?api-version={api_version}"
            )

        # Construct the full URL for validation
        test_url = construct_test_url(api_endpoint, deployment_name, api_version)
        logger.debug("Validating API endpoint and deployment.")

        # Prepare the test request payload
        test_payload: Dict[str, Any] = {
            "messages": [{"role": "user", "content": "Test message"}],
            "max_tokens": 1,
        }

        # Configure payload for o1-preview models
        if api_version.endswith("-preview"):
            test_payload["temperature"] = 1.0  # Required for o1-preview
            test_payload["max_completion_tokens"] = 1
            test_payload.pop("max_tokens", None)

        # Make the test request
        response = requests.post(
            test_url, headers={"api-key": api_key}, json=test_payload, timeout=10
        )
        return response.status_code == 200
    except requests.exceptions.Timeout:
        logger.error("Validation failed due to a timeout.")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Validation failed with a request exception: {str(e)}")
        raise
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during API endpoint validation: {str(e)}"
        )
        raise