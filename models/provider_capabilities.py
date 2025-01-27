"""
Module for managing provider capabilities.

This module provides a gradual path to multi-provider support by defining
provider-specific capabilities and validation rules that can be integrated
into the existing provider system.
"""

from typing import Dict, Any, Optional, List

# Default Azure capabilities - matches current system behavior
AZURE_CAPABILITIES = {
    "name": "azure",
    "endpoint_pattern": "https://{deployment}.openai.azure.com/openai/deployments/{model}",
    "supports_streaming": True,
    "max_tokens": 16384,
    "api_version": "2023-07-01-preview",
    "validation_rules": {
        "endpoint": r"^https://[a-zA-Z0-9-]+\.openai\.azure\.com/.*$",
        "model_identifier": r"^[a-zA-Z0-9-]+$"
    }
}

def get_provider_capabilities(provider_slug: str) -> Dict[str, Any]:
    """
    Get capabilities for a specific provider.
    Currently only supports 'azure' for backward compatibility.

    Args:
        provider_slug: Provider identifier (e.g. 'azure')

    Returns:
        Dict containing provider capabilities
    """
    # For now, only return Azure capabilities
    # This function will be expanded as we add more providers
    return AZURE_CAPABILITIES.copy()

def validate_endpoint(provider_slug: str, endpoint: str) -> List[str]:
    """
    Validate an API endpoint for a specific provider.
    Currently maintains existing Azure validation.

    Args:
        provider_slug: Provider identifier
        endpoint: API endpoint to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # For now, maintain existing Azure-specific validation
    if not endpoint.startswith("https://"):
        errors.append("API endpoint must use HTTPS")
    if "openai.azure.com" not in endpoint:
        errors.append("Invalid Azure OpenAI endpoint")

    return errors

def format_endpoint(provider_slug: str, **kwargs) -> str:
    """
    Format an API endpoint using provider-specific pattern.
    Currently maintains Azure endpoint format.

    Args:
        provider_slug: Provider identifier
        **kwargs: Format parameters (e.g. deployment, model)

    Returns:
        Formatted endpoint URL
    """
    capabilities = get_provider_capabilities(provider_slug)
    pattern = capabilities["endpoint_pattern"]

    try:
        return pattern.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing required endpoint parameter: {e}")
