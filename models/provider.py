import json
import re
from typing import Optional, Dict, Any, List
from sqlalchemy import Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy.sql import func
from logging_config import get_logger
from .base import Base

# Use the standardized logger
logger = get_logger(__name__)

# Type alias for clarity
ProviderDict = Dict[str, Any]

class Provider(Base):
    """
    Represents an AI provider configuration using SQLAlchemy ORM.
    
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
        is_active: Whether the provider is currently active
        capabilities: Provider capabilities configuration
        created_at: Creation timestamp
        api_key: Optional provider-level API key
        model_name: Optional default model name
        deployment_name: Optional default deployment name (Azure only)
        is_azure: Whether this is an Azure OpenAI provider
    """
    __tablename__ = "providers"

    # Required fields without defaults
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    api_base_url: Mapped[str] = mapped_column(String(200), nullable=False)
    api_version_format: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Fields with defaults
    auth_type: Mapped[str] = mapped_column(String(20), nullable=False, default="api-key")
    endpoint_pattern: Mapped[str] = mapped_column(String(200), nullable=True, default="")
    validation_rules: Mapped[str] = mapped_column(Text, nullable=True, default="{}")
    requires_authentication: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=True, default=lambda: {})
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Optional fields
    api_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    deployment_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_azure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship back to models
    models = relationship("Model", back_populates="provider", lazy="select", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        """
        Initialize the Provider instance.
        If capabilities or validation_rules are provided as dicts, they are stored as JSON strings.
        """
        # Handle both string and dict inputs
        if 'capabilities' in kwargs:
            # Ensure capabilities is always a dict
            if isinstance(kwargs['capabilities'], str):
                try:
                    kwargs['capabilities'] = json.loads(kwargs['capabilities'])
                except json.JSONDecodeError:
                    kwargs['capabilities'] = {}
            elif not isinstance(kwargs['capabilities'], dict):
                kwargs['capabilities'] = {}

        if 'validation_rules' in kwargs:
            if isinstance(kwargs['validation_rules'], dict):
                kwargs['validation_rules'] = json.dumps(kwargs['validation_rules'])
            elif isinstance(kwargs['validation_rules'], str):
                try:  # Parse if already in string format
                    kwargs['validation_rules'] = json.dumps(json.loads(kwargs['validation_rules']))
                except json.JSONDecodeError:
                    kwargs['validation_rules'] = "{}"

        # Set appropriate defaults based on provider type
        if kwargs.get("is_azure") or "openai.azure.com" in kwargs.get("api_base_url", ""):
            kwargs["is_azure"] = True
            kwargs.setdefault("endpoint_pattern", "https://{endpoint}/openai/deployments/{deployment}/chat/completions")
            kwargs.setdefault("validation_rules", json.dumps({
                "model_id": "^[a-zA-Z0-9-]{3,64}$",
                "api_version": r"^\d{4}-\d{2}-\d{2}(-preview)?$"
            }))
        else:
            kwargs.setdefault("endpoint_pattern", "https://api.openai.com/v1/chat/completions")
            kwargs.setdefault("validation_rules", json.dumps({
                "model_id": "^(gpt-4|gpt-3.5-turbo).*$",
                "api_version": "^v[0-9]+.*$"
            }))

        super().__init__(**kwargs)

    def get_capabilities(self) -> dict:
        """Return the capabilities as a dictionary."""
        try:
            return json.loads(self.capabilities) if self.capabilities else {}
        except Exception as e:
            logger.error("Error parsing capabilities for provider %s: %s", self.id, e)
            return {}

    def get_validation_rules(self) -> dict:
        """Return the validation_rules as a dictionary."""
        try:
            return json.loads(self.validation_rules) if self.validation_rules else {}
        except Exception as e:
            logger.error("Error parsing validation rules for provider %s: %s", self.id, e)
            return {}

    def validate_model_id(self, model_id: str) -> bool:
        """Validate a model ID against the provider's validation rules."""
        if not isinstance(model_id, str):
            raise TypeError("model_id must be a string")
        if not model_id:
            return False
        rules = self.get_validation_rules()
        pattern = rules.get("model_id")
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
    def get_by_id(session: Session, provider_id: int) -> Optional["Provider"]:
        """Retrieve a provider by its ID."""
        try:
            provider = session.query(Provider).filter_by(id=provider_id).first()
            if provider:
                # Parse JSON fields if they exist as strings
                if isinstance(provider.capabilities, str):
                    provider.capabilities = json.loads(provider.capabilities)
                if isinstance(provider.validation_rules, str):
                    provider.validation_rules = json.loads(provider.validation_rules)
            return provider
        except Exception as e:
            logger.error("Error retrieving provider by ID %d: %s", provider_id, e)
            return None

    @staticmethod
    def get_all(session: Session) -> List["Provider"]:
        """Retrieve all providers."""
        try:
            return session.query(Provider).order_by(Provider.name).all()
        except Exception as e:
            logger.error("Error retrieving all providers: %s", e)
            return []

    @staticmethod
    def get_by_slug(session: Session, slug: str) -> Optional["Provider"]:
        """Retrieve a provider by its slug."""
        try:
            provider = session.query(Provider).filter_by(slug=slug).first()
            if provider:
                # Parse JSON fields if they exist as strings
                if isinstance(provider.capabilities, str):
                    provider.capabilities = json.loads(provider.capabilities)
                if isinstance(provider.validation_rules, str):
                    provider.validation_rules = json.loads(provider.validation_rules)
            return provider
        except Exception as e:
            logger.error("Error retrieving provider by slug %s: %s", slug, e)
            return None

    @staticmethod
    def create(session: Session, data: ProviderDict) -> Optional[int]:
        """Create a new provider record."""
        try:
            logger.debug("Creating provider with data: %s", {k: v if k != "api_key" else "****" for k, v in data.items()})
            
            # Check for existing provider with same name or slug
            existing = session.query(Provider).filter(
                (func.lower(Provider.name) == func.lower(data["name"])) |
                (func.lower(Provider.slug) == func.lower(data["slug"]))
            ).first()
            
            if existing:
                field = "name" if existing.name.lower() == data["name"].lower() else "slug"
                raise ValueError(f"A provider with this {field} already exists")

            # Handle API key encryption if provided
            if data.get("api_key"):
                from config import config_instance
                from utils.encryption import encrypt_api_key
                data["api_key"] = encrypt_api_key(data["api_key"], config_instance.ENCRYPTION_KEY)

            # Create new provider instance
            provider = Provider(**data)
            session.add(provider)
            session.flush()  # Get the ID without committing
            
            provider_id = provider.id
            logger.info("Provider created with ID: %d", provider_id)
            return provider_id

        except Exception as e:
            logger.error("Failed to create provider: %s", e)
            raise
