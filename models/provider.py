"""
Module for handling provider operations.

This module provides a Provider class for managing AI provider configurations, including:
- CRUD operations for provider records
- Provider validation and configuration
"""

import re
import json
from typing import Optional, Dict, Any, List
from sqlalchemy import text

# (Remove the import line entirely)
from utils.encryption import encrypt_api_key
from logging_config import get_logger

logger = get_logger(__name__)

# Type alias for clarity
ProviderDict = Dict[str, Any]

# Default Azure settings – updated to use a newer API version
DEFAULT_SETTINGS = {
    "supports_streaming": True,
    "max_tokens": 16384,
    "api_version": "2025-01-01-preview",  # updated default
    "endpoint_pattern": "https://{deployment}.openai.azure.com/openai/deployments/{model}",
}

# Default provider capabilities
DEFAULT_CAPABILITIES = {
    "temperature_range": {"min": 0.0, "max": 2.0, "default": 1.0},
    "max_tokens": 2048,
    "streaming": False,
    "endpoint_pattern": "https://{region}.api.{domain}/{version}",
    "supported_api_versions": [],
    "supported_models": [],
    "features": [],
    "validation_rules": {
        "endpoint": r"^https://[a-zA-Z0-9-]+\.api\.[a-zA-Z0-9-]+\.[a-zA-Z0-9-]+/[a-zA-Z0-9-]+$",
        "model_identifier": r"^[a-zA-Z0-9-]+$",
    },
}


class ProviderCapabilities:
    """Helper class for managing provider capabilities."""

    def __init__(self, capabilities: Dict[str, Any]):
        # Merge the incoming dict with the global defaults
        self.capabilities: Dict[str, Any] = {**DEFAULT_CAPABILITIES, **capabilities}

    def supports_feature(self, feature: str) -> bool:
        """
        Check if provider supports a specific feature.

        Args:
            feature: Name of the feature to check

        Returns:
            bool: True if feature is supported, False otherwise
        """
        features: List[str] = self.capabilities.get("features", [])
        if not isinstance(features, list):
            return False
        return feature in features

    def get_validation_rule(self, rule_name: str) -> Optional[str]:
        """Get a validation rule pattern."""
        return self.capabilities.get("validation_rules", {}).get(rule_name)

    def get_endpoint_pattern(self) -> str:
        """Get the endpoint URL pattern."""
        return self.capabilities.get(
            "endpoint_pattern", DEFAULT_CAPABILITIES["endpoint_pattern"]
        )

    def validate_model_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate model configuration against provider capabilities."""
        errors = []
        temp_range = self.capabilities.get("temperature_range", {})
        if "temperature" in config:
            temp = config["temperature"]
            if temp < temp_range.get("min", 0.0) or temp > temp_range.get("max", 2.0):
                errors.append(
                    f"Temperature must be between {temp_range['min']} and {temp_range['max']}"
                )
        max_tokens = self.capabilities.get("max_tokens")
        if "max_tokens" in config and max_tokens:
            if config["max_tokens"] > max_tokens:
                errors.append(f"Max tokens cannot exceed {max_tokens}")
        if "model_identifier" in config:
            pattern = self.get_validation_rule("model_identifier")
            if pattern and not re.match(pattern, config["model_identifier"]):
                errors.append("Invalid model identifier format")
        return errors


@dataclass
class Provider:
    """
    Represents an AI provider configuration.

    Attributes:
        id: Unique identifier for the provider
        name: Display name of the provider
        slug: URL-friendly identifier
        api_base_url: Base URL for provider's API
        api_version_format: Format string for API version
        auth_type: Authentication type ('api-key', 'oauth', etc.)
        endpoint_pattern: Template for model endpoints
        validation_rules: Regex patterns for validating models
        requires_authentication: Whether provider requires authentication
        capabilities: Provider capabilities configuration
        created_at: Creation timestamp
        api_key: Optional provider-level API key
        model_name: Optional default model name
        deployment_name: Optional default deployment name (Azure only)
        is_azure: Whether this is an Azure OpenAI provider
    """

    id: int
    name: str
    slug: str
    api_base_url: str
    api_version_format: str
    auth_type: str = "api-key"
    endpoint_pattern: str = field(default_factory=lambda: "")
    validation_rules: Dict[str, str] = field(default_factory=lambda: {})
    requires_authentication: bool = field(default=True)
    is_active: bool = field(default=True)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    deployment_name: Optional[str] = None
    is_azure: bool = False

    def __post_init__(self):
        """Set appropriate defaults based on provider type."""
        if isinstance(self.capabilities, str):
            self.capabilities = json.loads(self.capabilities)

        # Heuristic check for Azure usage
        if self.is_azure or "openai.azure.com" in self.api_base_url:
            # If is_azure, set typical Azure endpoint pattern and validation rules
            self.endpoint_pattern = (
                "https://{endpoint}/openai/deployments/{deployment}/chat/completions"
            )
            # updated to match typical Azure preview pattern
            self.validation_rules = {
                "model_id": "^[a-zA-Z0-9-]{3,64}$",
                "api_version": r"^\d{4}-\d{2}-\d{2}(-preview)?$",
            }
        else:
            # Otherwise, assume standard OpenAI
            self.endpoint_pattern = "https://api.openai.com/v1/chat/completions"
            self.validation_rules = {
                "model_id": "^(gpt-4|gpt-3.5-turbo).*$",
                "api_version": "^v[0-9]+.*$",
            }

    def validate_model_id(self, model_id: str) -> bool:
        if not isinstance(model_id, str):
            raise TypeError("model_id must be a string")
        if not model_id:
            return False
        pattern = self.validation_rules.get("model_id")
        if not pattern:
            return True
        return bool(re.fullmatch(pattern, model_id))

    def format_model_endpoint(self, deployment: str, model: str) -> str:
        """Format endpoint using provider's pattern."""
        return self.endpoint_pattern.format(
            deployment=deployment,
            model=model,
            provider=self.slug,
            api_version=self.api_version_format,
        )

    @staticmethod
    def create(session: Session, data: ProviderDict) -> Optional[int]:
        """Create a new provider record using the provided session."""
        try:
            logger.debug("Creating provider with data: %s", data)
            check_query = text(
                    """
                    SELECT name, slug
                    FROM providers
                    WHERE LOWER(name) = LOWER(:name)
                    OR LOWER(slug) = LOWER(:slug)
                    """
                )
            existing = session.execute(
                check_query,
                {"name": data["name"], "slug": data["slug"]},
            ).fetchone()

            if existing:
                    field = (
                        "name"
                        if existing[0].lower() == data["name"].lower()
                        else "slug"
                    )
                    raise ValueError(f"A provider with this {field} already exists")

            data = data.copy()
            # Convert dict to JSON if needed
            if isinstance(data.get("capabilities"), dict):
                data["capabilities"] = json.dumps(data["capabilities"])

            api_key = data.get("api_key")
            if api_key:
                from config import config_instance
                api_key = encrypt_api_key(api_key, config_instance.ENCRYPTION_KEY)

                # Check if it's an Azure-based provider
                is_azure = data.get("is_azure", False) or "openai.azure.com" in data.get("api_base_url", "")
                if is_azure:
                    # Updated default endpoint pattern and validation for Azure
                    endpoint_pattern = "https://{endpoint}/openai/deployments/{deployment}/chat/completions"
                    validation_rules = {
                        "model_id": "^[a-zA-Z0-9-]{3,64}$",
                        "api_version": r"^\d{4}-\d{2}-\d{2}(-preview)?$",
                    }
                    # Also update to a newer API version if not provided
                    if not data.get("api_version_format"):
                        data["api_version_format"] = "2025-01-01-preview"
                else:
                    endpoint_pattern = "https://api.openai.com/v1/chat/completions"
                    validation_rules = {
                        "model_id": "^(gpt-4|gpt-3.5-turbo).*$",
                        "api_version": "^v[0-9]+.*$",
                    }

                query = text(
                    """
                    INSERT INTO providers (
                        name, slug, api_base_url, capabilities,
                        requires_authentication, api_version_format,
                        endpoint_pattern, auth_type, validation_rules,
                        api_key, model_name, deployment_name, is_azure
                    ) VALUES (
                        :name, :slug, :api_base_url, :capabilities,
                        :requires_authentication, :api_version_format,
                        :endpoint_pattern, :auth_type, :validation_rules,
                        :api_key, :model_name, :deployment_name, :is_azure
                    )
                    RETURNING id
                    """
                )

                result = session.execute(
                    query,
                    {
                        "name": data["name"],
                        "slug": data["slug"],
                        "api_base_url": data["api_base_url"],
                        "capabilities": data.get("capabilities", "{}"),
                        "requires_authentication": data.get("requires_authentication", True),
                        "api_version_format": data.get("api_version_format"),
                        "endpoint_pattern": data.get("endpoint_pattern", endpoint_pattern),
                        "auth_type": data.get("auth_type", "api-key"),
                        "validation_rules": json.dumps(
                            data.get("validation_rules", validation_rules)
                        ),
                        "api_key": api_key,
                        "model_name": data.get("model_name"),
                        "deployment_name": (data.get("deployment_name") if is_azure else None),
                        "is_azure": is_azure,
                    },
                )
                provider_id = result.scalar()
                if provider_id is None:
                    logger.error("Failed to create provider - no ID returned")
                    return None
                logger.info("Provider created with ID: %d", provider_id)
                return provider_id

        except Exception as e:
            logger.error("Failed to create provider: %s", e)
            raise

    @staticmethod
    def get_by_id(session: Session, provider_id: int) -> Optional["Provider"]:
        """Retrieve a provider by its ID using the provided session."""
        try:
            query = text("SELECT * FROM providers WHERE id = :id")
            row = session.execute(query, {"id": provider_id}).mappings().first()
            if not row:
                logger.warning("No provider found with ID %s", provider_id)
                return None
            return Provider(**dict(row))
        except Exception as e:
            logger.error("Error retrieving provider by ID %d: %s", provider_id, e)
            return None

    @staticmethod
    def get_all(session: Session) -> List["Provider"]:
        """Retrieve all providers using the provided session."""
        try:
            query = text("SELECT * FROM providers ORDER BY name")
            rows = session.execute(query).mappings().all()
            return [Provider(**dict(row)) for row in rows]
        except Exception as e:
            logger.error("Error retrieving providers: %s", e)
            raise

    @staticmethod
    def get_by_slug(session: Session, slug: str) -> Optional["Provider"]:
        """Retrieve a provider by its slug using the provided session."""
        try:
            query = text("SELECT * FROM providers WHERE slug = :slug")
            row = session.execute(query, {"slug": slug}).mappings().first()
            if not row:
                logger.warning("No provider found with slug %s", slug)
                return None
                return Provider(**dict(row))
        except Exception as e:
            logger.error("Error retrieving provider by slug %s: %s", slug, e)
            return None
