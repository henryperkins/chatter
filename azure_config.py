"""Azure OpenAI configuration and client management module."""

import os
import requests
from typing import Dict, Optional, Tuple, Any
from urllib.parse import urlparse

from openai import AzureOpenAI
from config import MODEL_CONFIG
from logging_config import get_logger

logger = get_logger(__name__)

# Constants
DEFAULT_API_VERSION = "2024-02-01"  # Default for client creation
DEFAULT_TIMEOUT = 30
API_URL_PATTERN = "{endpoint}/openai/deployments/{deployment}/chat/completions"
VALID_REASONING_EFFORTS = ["low", "medium", "high"]


def validate_api_version(model_type: str, api_version: str) -> bool:
    """
    Validate API version compatibility for different model types.
    
    Args:
        model_type: The type of model (e.g., 'o3-mini', 'o1', 'o1-preview')
        api_version: The API version to validate
        
    Returns:
        bool: True if version is valid for model type, False otherwise
    """
    version_matrix = {
        "o3-mini": ["2024-12-01-preview", "2025-01-01-preview"],
        "o1": ["2024-12-01-preview", "2025-01-01-preview"],
        "o1-preview": ["2024-09-01-preview", "2024-10-01-preview", "2024-12-01-preview"],
        "o1-mini": ["2024-09-01-preview", "2024-10-01-preview", "2024-12-01-preview"]
    }
    return api_version in version_matrix.get(model_type.lower(), [])

def validate_model_config(model_config: Dict[str, Any]) -> None:
    """
    Validate model configuration and enforce model-specific requirements.
    Uses the standardized MODEL_CONFIG based on model_type.
    """
    if not isinstance(model_config, dict):
        raise ValueError("model_config must be a dictionary")
        
    # Validate API version compatibility
    model_type = model_config.get("model_type")
    api_version = model_config.get("api_version")
    if model_type and api_version:
        if not validate_api_version(model_type, api_version):
            raise ValueError(f"Invalid API version {api_version} for model type {model_type}")

    # Required fields validation with proper type checking
    required_fields = {"api_endpoint", "api_key", "deployment_name", "api_version"}
    for field in required_fields:
        value = model_config.get(field)
        if not value or not isinstance(value, str):
            raise ValueError(f"Missing or invalid {field}")

    # Safe model_type access and validation
    model_type = model_config.get("model_type")
    if not model_type or not isinstance(model_type, str):
        raise ValueError("model_type is required and must be a string")

    model_caps = MODEL_CONFIG.get(model_type)
    if not model_caps:
        raise ValueError(f"Unsupported model_type: {model_type}")

    # Check if model is o-series
    is_o_series = model_type.startswith("o")

    if is_o_series:
        # O-series specific validation
        if "temperature" in model_config or "top_p" in model_config:
            raise ValueError("temperature and top_p are not supported by o-series models")

        # Validate reasoning_effort if provided
        if "reasoning_effort" in model_config:
            effort = model_config["reasoning_effort"]
            if effort not in VALID_REASONING_EFFORTS:
                raise ValueError(f"reasoning_effort must be one of {VALID_REASONING_EFFORTS}")
    else:
        # Legacy model validation
        if "temperature" in model_config:
            try:
                temp = float(model_config["temperature"])
                if not 0 <= temp <= 2:
                    raise ValueError("Temperature must be between 0 and 2")
                model_config["temperature"] = temp
            except (TypeError, ValueError):
                raise ValueError("Temperature must be a number between 0 and 2")

        if "reasoning_effort" in model_config:
            raise ValueError("reasoning_effort is only supported by o-series models")

    # Validate token parameters
    if "max_tokens" in model_config and "max_completion_tokens" in model_config:
        raise ValueError("Cannot specify both max_tokens and max_completion_tokens")

    if "max_completion_tokens" in model_config:
        try:
            max_completion = int(model_config["max_completion_tokens"])
            if max_completion < 256:
                raise ValueError("max_completion_tokens must be >= 256")
            model_config["max_completion_tokens"] = max_completion  # Store converted value
        except (TypeError, ValueError):
            raise ValueError("max_completion_tokens must be an integer >= 256")

    # Validate response_format
    if "response_format" in model_config:
        response_format = model_config.get("response_format")
        if not isinstance(response_format, dict):
            raise ValueError("response_format must be an object")

        format_type = response_format.get("type")
        if not format_type or format_type not in ["text", "json_object"]:
            raise ValueError("response_format.type must be 'text' or 'json_object'")


def create_client(
    api_endpoint: str,
    api_key: str,
    api_version: str = DEFAULT_API_VERSION,
    timeout: int = DEFAULT_TIMEOUT,
) -> AzureOpenAI:
    """
    Create a properly configured Azure OpenAI client with validated configuration
    (using only API Key authentication).
    """
    # Validate input parameters
    if not api_endpoint or not isinstance(api_endpoint, str):
        raise ValueError("Invalid API endpoint")
    if not api_key or not isinstance(api_key, str):
        raise ValueError("Invalid API key")
    if not api_version or not isinstance(api_version, str):
        raise ValueError("Invalid API version")

    logger.info("Validating API endpoint format")
    # The endpoint should not include a deployments path.
    if "/openai/deployments/" in api_endpoint:
        logger.error("Invalid endpoint contains deployments path: %s", api_endpoint)
        raise ValueError("Endpoint should be a base URL without deployments path")

    # Clean and validate the endpoint URL
    api_endpoint = api_endpoint.rstrip("/")
    try:
        parsed = urlparse(api_endpoint)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid API endpoint URL format")
        # Construct full endpoint URL: append '/openai' if the path does not already start with it.
        if not parsed.path.startswith("/openai"):
            api_endpoint = f"{api_endpoint}/openai"
    except Exception as e:
        raise ValueError(f"Invalid API endpoint URL: {str(e)}")

    logger.debug("Creating Azure OpenAI client with endpoint: %s", api_endpoint)

    # Prepare client configuration
    client_kwargs = {
        "azure_endpoint": api_endpoint,
        "api_version": api_version.strip(),
        "timeout": timeout,
        "api_key": api_key,
    }

    try:
        client = AzureOpenAI(**client_kwargs)
        logger.debug("Created Azure OpenAI client using API key authentication.")
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to create Azure OpenAI client: {str(e)}")


def initialize_client_from_model(
    model_config: Dict[str, Any], timeout_seconds: int = DEFAULT_TIMEOUT
) -> Tuple[AzureOpenAI, str, Optional[float], Optional[int], int, bool, Optional[str]]:
    """
    Initialize Azure OpenAI client from model configuration.
    """
    # Validate model configuration first
    validate_model_config(model_config)

    # Required fields (already validated)
    api_endpoint = str(model_config["api_endpoint"])
    api_key = str(model_config["api_key"])
    deployment_name = str(model_config["deployment_name"])
    api_version = str(model_config["api_version"])

    # Handle temperature
    temperature = None
    if "temperature" in model_config:
        try:
            temperature = float(model_config["temperature"])
        except (TypeError, ValueError):
            raise ValueError("Invalid temperature value")

    # Handle tokens
    max_tokens = None
    if "max_tokens" in model_config:
        try:
            max_tokens = int(model_config["max_tokens"])
        except (TypeError, ValueError):
            raise ValueError("Invalid max_tokens value")

    max_completion_tokens = 500  # Default value
    if "max_completion_tokens" in model_config:
        try:
            max_completion_tokens = int(model_config["max_completion_tokens"])
        except (TypeError, ValueError):
            raise ValueError("Invalid max_completion_tokens value")

    # Handle reasoning effort for o-series models
    reasoning_effort = None
    if model_config.get("model_type", "").startswith("o"):
        reasoning_effort = model_config.get("reasoning_effort", "medium")
        if reasoning_effort not in VALID_REASONING_EFFORTS:
            raise ValueError(
                f"Invalid reasoning_effort. Must be one of {VALID_REASONING_EFFORTS}"
            )

    client = create_client(
        api_endpoint=api_endpoint,
        api_key=api_key,
        api_version=api_version,
        timeout=timeout_seconds,
    )

    requires_o1 = bool(model_config.get("requires_o1_handling", False))

    return (
        client,
        deployment_name,
        temperature,
        max_tokens,
        max_completion_tokens,
        requires_o1,
        reasoning_effort
    )


def validate_api_endpoint(
    api_endpoint: str,
    api_key: str,
    deployment_name: str,
    api_version: str = DEFAULT_API_VERSION,
) -> Dict[str, Any]:
    """
    Validate Azure OpenAI endpoint by making a test request.
    """
    if not all([api_endpoint, api_key, deployment_name]):
        return {"success": False, "error": "Missing required parameters"}

    try:
        base_url = api_endpoint.strip().rstrip("/")
        url = f"{base_url}/openai/deployments/{deployment_name}/chat/completions"
        url = f"{url}?api-version={api_version.strip()}"

        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc, parsed.path]):
            return {"success": False, "error": "Invalid API endpoint URL format"}

        # Determine if testing o-series model
        is_o_series = any(
            deployment_name.startswith(prefix)
            for prefix in ["o1", "o3"]
        )

        messages = [
            {"role": "developer", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Test message"}
        ]

        if is_o_series:
            # O-series specific payload
            payload = {
                "messages": messages,
                "max_completion_tokens": 1,
                "reasoning_effort": "medium",
                "stream": False,
                "temperature": 1.0  # For demonstration
            }
        else:
            # Legacy model payload
            payload = {
                "messages": messages,
                "max_tokens": 1,
                "temperature": 1.0,
                "top_p": 1.0,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "stream": False
            }

        response = requests.post(
            url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )

        if response.status_code == 200:
            try:
                response_data = response.json()
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    return {"success": True}
                return {"success": False, "error": "Invalid response format from API"}
            except ValueError:
                return {"success": False, "error": "Invalid JSON response from API"}

        error_message = f"API returned status code: {response.status_code}"
        try:
            error_data = response.json()
            if isinstance(error_data, dict) and "error" in error_data:
                error_details = error_data["error"]
                if isinstance(error_details, dict):
                    error_message = f"{error_message} - {error_details.get('message', '')}"
        except Exception:
            pass

        return {"success": False, "error": error_message}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timed out. Check your network connection."}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def get_azure_client(deployment_name: Optional[str] = None) -> Tuple[AzureOpenAI, str]:
    """
    Get Azure OpenAI client with optional deployment override from environment.
    """
    if not deployment_name:
        deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    if not deployment_name:
        raise ValueError("Deployment name not provided or found in environment")

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = os.getenv("AZURE_OPENAI_KEY", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION).strip()

    if not endpoint or not api_key:
        raise ValueError("Missing required Azure OpenAI configuration")

    client = create_client(
        api_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    return client, deployment_name
