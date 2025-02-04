"""Azure OpenAI configuration and client management module."""

import os
import requests
import logging
from typing import Dict, Optional, Tuple, Any, List
from config import MODEL_CONFIG
from logging_config import get_logger

logger = get_logger(__name__)

# Constants
DEFAULT_API_VERSION = "2024-12-01-preview"
DEFAULT_TIMEOUT = 30
API_URL_PATTERN = "{endpoint}/openai/deployments/{deployment}/chat/completions"


def validate_model_config(model_config: Dict[str, Any]) -> None:
    """
    Validate model configuration and enforce model-specific requirements.
    Uses the standardized MODEL_CONFIG based on model_type.
    """
    model_type = model_config.get("model_type")
    model_caps = MODEL_CONFIG.get(model_type, {})

    # Required fields validation
    required_fields = {"api_endpoint", "api_key", "deployment_name", "api_version"}
    missing_fields = [field for field in required_fields if not model_config.get(field)]
    if missing_fields:
        raise ValueError(
            f"Missing required configuration parameters: {', '.join(missing_fields)}"
        )

    # o1-preview specific validation
    if model_config.get("requires_o1_handling"):
        if not model_config["api_version"].endswith("-preview"):
            model_config["api_version"] = model_caps.get(
                "api_version", DEFAULT_API_VERSION
            )
        if model_config.get("temperature") not in (None, 1, 1.0):
            model_config["temperature"] = 1.0
        if model_config.get("max_tokens"):
            del model_config["max_tokens"]
        if model_config.get("stream"):
            model_config["stream"] = False
        # Filter system messages if present
        messages = model_config.get("messages", [])
        if messages:
            model_config["messages"] = [
                msg for msg in messages if msg.get("role") != "system"
            ]


def create_client(
    api_endpoint: str,
    api_key: str,
    api_version: str = DEFAULT_API_VERSION,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Create an Azure OpenAI client with validated configuration.
    """
    if not api_endpoint or not api_key:
        raise ValueError("API endpoint and key are required")
    from openai import AzureOpenAI  # Import here to avoid circular dependency issues

    return AzureOpenAI(
        azure_endpoint=str(api_endpoint).rstrip("/"),
        api_key=str(api_key),
        api_version=str(api_version),
        timeout=timeout,
    )


def initialize_client_from_model(
    model_config: Dict[str, Any], timeout_seconds: int = DEFAULT_TIMEOUT
) -> Tuple[Any, str, Optional[float], Optional[int], int, bool]:
    """
    Initialize Azure OpenAI client from model configuration.
    """
    validate_model_config(model_config)

    api_endpoint = str(model_config["api_endpoint"])
    api_key = str(model_config["api_key"])
    deployment_name = str(model_config["deployment_name"])
    api_version = str(model_config["api_version"])
    requires_o1_handling = bool(model_config.get("requires_o1_handling", False))

    if requires_o1_handling:
        temperature = 1.0
        max_tokens = None
        max_completion_tokens = int(model_config.get("max_completion_tokens", 8500))
    else:
        temperature = (
            float(model_config.get("temperature"))
            if model_config.get("temperature") is not None
            else None
        )
        max_tokens = (
            int(model_config.get("max_tokens"))
            if model_config.get("max_tokens") is not None
            else None
        )
        max_completion_tokens = int(model_config.get("max_completion_tokens", 500))

    client = create_client(
        api_endpoint=api_endpoint,
        api_key=api_key,
        api_version=api_version,
        timeout=timeout_seconds,
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
    api_endpoint: str,
    api_key: str,
    deployment_name: str,
    api_version: str = DEFAULT_API_VERSION,
) -> Dict[str, Any]:
    """
    Validate Azure OpenAI endpoint by making a test request.
    """
    try:
        url = API_URL_PATTERN.format(
            endpoint=api_endpoint.rstrip("/"), deployment=deployment_name
        )
        url = f"{url}?api-version={api_version}"

        payload = {
            "messages": [{"role": "user", "content": "Test message"}],
            "max_tokens": 1,
        }

        if api_version.endswith("-preview"):
            payload.update({"temperature": 1.0, "max_completion_tokens": 1})
            payload.pop("max_tokens", None)

        response = requests.post(
            url, headers={"api-key": api_key}, json=payload, timeout=10
        )

        if response.status_code == 200:
            return {"success": True}

        return {
            "success": False,
            "error": f"API returned status code: {response.status_code}",
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out. Check your network connection.",
        }
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def get_azure_client(deployment_name: Optional[str] = None) -> Tuple[Any, str]:
    """
    Get Azure OpenAI client with optional deployment override.
    """
    deployment = deployment_name or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    if not deployment:
        raise ValueError("Deployment name not provided or found in environment")

    client = create_client(
        api_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        api_key=os.getenv("AZURE_OPENAI_KEY", ""),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION),
    )

    return client, deployment
