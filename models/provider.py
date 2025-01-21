"""
Module for handling provider operations.

This module provides a Provider class for managing AI provider configurations, including:
- CRUD operations for provider records
- Provider validation and configuration
"""
import re
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Pattern
from sqlalchemy import text

from database import db_session

logger = logging.getLogger(__name__)

# Type aliases for better readability
ProviderDict = Dict[str, Any]

# Default Azure settings - preserves current behavior
DEFAULT_SETTINGS = {
    "supports_streaming": True,
    "max_tokens": 16384,
    "api_version": "2023-07-01-preview",
    "endpoint_pattern": "https://{deployment}.openai.azure.com/openai/deployments/{model}"
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
        "model_identifier": r"^[a-zA-Z0-9-]+$"
    }
}

class ProviderCapabilities:
    """Helper class for managing provider capabilities."""

    def __init__(self, capabilities: Dict[str, Any]):
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
        return self.capabilities.get("endpoint_pattern", DEFAULT_CAPABILITIES["endpoint_pattern"])

    def validate_model_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate model configuration against provider capabilities."""
        errors = []

        # Validate temperature
        temp_range = self.capabilities.get("temperature_range", {})
        if "temperature" in config:
            temp = config["temperature"]
            if temp < temp_range.get("min", 0.0) or temp > temp_range.get("max", 2.0):
                errors.append(f"Temperature must be between {temp_range['min']} and {temp_range['max']}")

        # Validate tokens
        max_tokens = self.capabilities.get("max_tokens")
        if "max_tokens" in config and max_tokens:
            if config["max_tokens"] > max_tokens:
                errors.append(f"Max tokens cannot exceed {max_tokens}")

        # Validate model identifier
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
        capabilities: Provider-specific capabilities and constraints
        requires_authentication: Whether API key is required
        api_version_format: Format string for API version
        created_at: Creation timestamp
    """

    id: int
    name: str
    slug: str
    api_base_url: str
    capabilities: Dict[str, Any] = None
    requires_authentication: bool = True
    api_version_format: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        """Validate and adjust fields after initialization."""
        self.id = int(self.id)
        if self.capabilities is None:
            self.capabilities = DEFAULT_CAPABILITIES
        self._capabilities = ProviderCapabilities(self.capabilities)

    def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities helper."""
        return self._capabilities

    def validate_model(self, model_data: Dict[str, Any]) -> List[str]:
        """Validate model configuration against provider capabilities."""
        return self._capabilities.validate_model_config(model_data)

    def format_endpoint(self, **kwargs) -> str:
        """Format API endpoint using provider's pattern."""
        pattern = self._capabilities.get_endpoint_pattern()
        try:
            return pattern.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing required endpoint parameter: {e}")

    @staticmethod
    def create(data: ProviderDict) -> Optional[int]:
        """
        Create a new provider record.

        Args:
            data: Dictionary containing provider configuration

        Returns:
            Optional[int]: ID of created provider or None if creation failed

        Raises:
            ValueError: If provider configuration is invalid
        """
        try:
            with db_session() as session:
                logger.debug("Creating provider with data: %s", data)

                # Check for existing provider with same name or slug
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
                    {
                        "name": data["name"],
                        "slug": data["slug"]
                    },
                ).fetchone()

                if existing:
                    field = (
                        "name"
                        if existing[0].lower() == data["name"].lower()
                        else "slug"
                    )
                    raise ValueError(f"A provider with this {field} already exists")

                # Insert new provider
                query = text(
                    """
                    INSERT INTO providers (
                        name, slug, api_base_url, capabilities, requires_authentication,
                        api_version_format, created_at
                    ) VALUES (
                        :name, :slug, :api_base_url, :capabilities, :requires_authentication,
                        :api_version_format, NOW()
                    )
                    RETURNING id
                """
                )
                result = session.execute(query, data)
                provider_id = result.scalar()

                if provider_id is None:
                    logger.error("Failed to create provider - no ID returned")
                    return None

                session.commit()
                logger.info("Provider created with ID: %d", provider_id)
                return provider_id

        except Exception as e:
            logger.error("Failed to create provider: %s", e)
            raise

    @staticmethod
    def get_by_id(provider_id: int) -> Optional["Provider"]:
        """
        Retrieve a provider by its ID.

        Args:
            provider_id: ID of the provider to retrieve

        Returns:
            Optional[Provider]: Provider instance if found, None otherwise
        """
        try:
            with db_session() as session:
                query = text("SELECT * FROM providers WHERE id = :id")
                row = session.execute(query, {"id": provider_id}).mappings().first()

                if not row:
                    logger.warning("No provider found with ID %d", provider_id)
                    return None

                return Provider(**dict(row))

        except Exception as e:
            logger.error("Error retrieving provider by ID %d: %s", provider_id, e)
            return None

    @staticmethod
    def get_all() -> List["Provider"]:
        """
        Retrieve all providers.

        Returns:
            List[Provider]: List of provider instances
        """
        with db_session() as session:
            try:
                query = text("SELECT * FROM providers ORDER BY name")
                rows = session.execute(query).mappings().all()
                return [Provider(**dict(row)) for row in rows]
            except Exception as e:
                logger.error("Error retrieving providers: %s", e)
                raise

    @staticmethod
    def get_by_slug(slug: str) -> Optional["Provider"]:
        """
        Retrieve a provider by its slug.

        Args:
            slug: URL-friendly identifier of the provider

        Returns:
            Optional[Provider]: Provider instance if found, None otherwise
        """
        try:
            with db_session() as session:
                query = text("SELECT * FROM providers WHERE slug = :slug")
                row = session.execute(query, {"slug": slug}).mappings().first()

                if not row:
                    logger.warning("No provider found with slug %s", slug)
                    return None

                return Provider(**dict(row))

        except Exception as e:
            logger.error("Error retrieving provider by slug %s: %s", slug, e)
            return None
