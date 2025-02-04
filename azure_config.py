"""Azure OpenAI configuration and client management module."""

import os
from typing import Dict, Optional, Tuple, Any
import requests
from openai import AzureOpenAI
from urllib.parse import urlparse, urlunparse

from config import MODEL_CONFIG
from logging_config import get_logger

logger = get_logger(__name__)

# Constants
DEFAULT_API_VERSION = "2025-01-01-preview"
DEFAULT_TIMEOUT = 30
API_URL_PATTERN = "{endpoint}/openai/deployments/{deployment}/chat/completions"


def validate_model_config(model_config: Dict[str, Any]) -> None:
    """
    Validate model configuration and enforce model-specific requirements.
    Uses the standardized MODEL_CONFIG based on model_type.
    """
    if not isinstance(model_config, dict):
        raise ValueError("model_config must be a dictionary")

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

    # Validate numeric parameters with proper type conversion
    if "temperature" in model_config:
        try:
            temp = float(model_config["temperature"])
            if not 0 <= temp <= 2:
                raise ValueError("Temperature must be between 0 and 2")
            model_config["temperature"] = temp  # Store converted value
        except (TypeError, ValueError):
            raise ValueError("Temperature must be a number between 0 and 2")

    if "top_p" in model_config:
        try:
            top_p = float(model_config["top_p"])
            if not 0 <= top_p <= 1:
                raise ValueError("top_p must be between 0 and 1")
            model_config["top_p"] = top_p  # Store converted value
        except (TypeError, ValueError):
            raise ValueError("top_p must be a number between 0 and 1")

    # Validate token parameters
    if "max_tokens" in model_config and "max_completion_tokens" in model_config:
        raise ValueError("Cannot specify both max_tokens and max_completion_tokens")

    if "max_completion_tokens" in model_config:
        try:
            max_completion = int(model_config["max_completion_tokens"])
            if max_completion < 256:
                raise ValueError("max_completion_tokens must be >= 256")
            model_config["max_completion_tokens"] = (
                max_completion  # Store converted value
            )
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
    Create an Azure OpenAI client with validated configuration.
    """
    if not api_endpoint or not isinstance(api_endpoint, str):
        raise ValueError("Invalid API endpoint")
    if not api_key or not isinstance(api_key, str):
        raise ValueError("Invalid API key")
    if not api_version or not isinstance(api_version, str):
        raise ValueError("Invalid API version")

    # Clean and validate endpoint URL
    api_base = api_endpoint.rstrip("/")
    try:
        parsed = urlparse(api_base)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid API endpoint URL format")
        api_base = urlunparse(parsed)  # Normalize URL
    except Exception as e:
        raise ValueError(f"Invalid API endpoint URL: {str(e)}")

    logger.debug("Creating Azure OpenAI client with endpoint: %s", api_base)

    try:
        client = AzureOpenAI(
            azure_endpoint=api_base,
            api_key=api_key,
            api_version=api_version.strip(),
            timeout=timeout,
        )
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to create Azure OpenAI client: {str(e)}")


def initialize_client_from_model(
    model_config: Dict[str, Any], timeout_seconds: int = DEFAULT_TIMEOUT
) -> Tuple[AzureOpenAI, str, Optional[float], Optional[int], int, bool]:
    """
    Initialize Azure OpenAI client from model configuration.
    """
    # Validate model configuration first
    validate_model_config(model_config)

    # Safe access to required fields (already validated)
    api_endpoint = str(model_config["api_endpoint"])
    api_key = str(model_config["api_key"])
    deployment_name = str(model_config["deployment_name"])
    api_version = str(model_config["api_version"])

    # Handle temperature with proper type conversion
    temperature = None
    if "temperature" in model_config:
        try:
            temperature = float(model_config["temperature"])
        except (TypeError, ValueError):
            raise ValueError("Invalid temperature value")

    # Handle tokens with proper type conversion
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
        # Properly construct and validate URL
        base_url = api_endpoint.strip().rstrip("/")
        url = f"{base_url}/openai/deployments/{deployment_name}/chat/completions"
        url = f"{url}?api-version={api_version.strip()}"

        # Validate URL format
        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc, parsed.path]):
            return {"success": False, "error": "Invalid API endpoint URL format"}

        payload = {
            "messages": [{"role": "user", "content": "Test message"}],
            "max_tokens": 1,
        }

        # Add API version specific parameters
        if api_version >= "2025-01-01-preview":
            payload.update(
                {
                    "temperature": 1.0,
                    "max_completion_tokens": 1,
                    "response_format": {"type": "text"},
                    "stream": False,
                }
            )

        response = requests.post(
            url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )

        if response.status_code == 200:
            return {"success": True}

        error_message = f"API returned status code: {response.status_code}"
        try:
            error_data = response.json()
            if "error" in error_data:
                error_message = (
                    f"{error_message} - {error_data['error'].get('message', '')}"
                )
        except Exception:
            pass

        return {"success": False, "error": error_message}

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out. Check your network connection.",
        }
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def get_azure_client(deployment_name: Optional[str] = None) -> Tuple[AzureOpenAI, str]:
    """
    Get Azure OpenAI client with optional deployment override.
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
