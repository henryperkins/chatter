"""
Module for handling model operations.

This module provides a Model class for managing AI model configurations, including:
- CRUD operations for model records
- Model validation and configuration
- Version control and history tracking
- Default model management
"""

import logging
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, cast, ClassVar
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet, InvalidToken

from sqlalchemy import text, Column, Integer, Float, Boolean, String, DateTime
from sqlalchemy.orm import mapped_column

from database import db_session
from .provider import Provider
from config import Config

logger = logging.getLogger(__name__)

# Type aliases for better readability
ModelDict = Dict[str, Any]

@dataclass
class Model:
    """
    Represents an AI model configuration.

    Attributes:
        id: Unique identifier for the model
        provider_id: ID of the provider this model belongs to
        name: Display name of the model
        deployment_name: Azure deployment name
        description: Model description
        model_type: Type of model (e.g., 'azure', 'o1-preview')
        api_endpoint: Azure API endpoint URL
        api_key: Encrypted API key
        temperature: Temperature setting for generation (0-2)
        max_tokens: Maximum tokens for completion
        max_completion_tokens: Maximum tokens for o1-preview models
        is_default: Whether this is the default model
        requires_o1_handling: Whether model needs o1-preview handling
        supports_streaming: Whether model supports streaming responses
        api_version: Azure API version
        created_at: Creation timestamp
    """

    id: int
    provider_id: int
    name: str
    deployment_name: str
    description: str
    model_type: str
    api_endpoint: str
    api_key: str
    temperature: Optional[float] = field(default=None, metadata={"sa": mapped_column(Float, nullable=True)})
    max_tokens: Optional[int] = field(default=None, metadata={"sa": mapped_column(Integer, nullable=True)})
    max_completion_tokens: Optional[int] = field(default=8300, metadata={"sa": mapped_column(Integer, nullable=False)})
    is_default: bool = field(default=False, metadata={"sa": mapped_column(Boolean, nullable=False)})
    requires_o1_handling: bool = field(default=False, metadata={"sa": mapped_column(Boolean, nullable=False)})
    supports_streaming: bool = field(default=False, metadata={"sa": mapped_column(Boolean, nullable=False)})
    api_version: str = field(default="2024-12-01-preview", metadata={"sa": mapped_column(String(50), nullable=False)})
    reasoning_effort: str = field(default="medium", metadata={"sa": mapped_column(String(10), nullable=False)})
    store_completion: bool = field(default=False, metadata={"sa": mapped_column(Boolean, nullable=False)})
    created_at: Optional[str] = field(default=None, metadata={"sa": mapped_column(DateTime, nullable=True)})
    version: int = field(default=1, metadata={"sa": mapped_column(Integer, nullable=False, server_default=text("1"))})

    # Class-level provider capabilities
    PROVIDER_CAPABILITIES: ClassVar[Dict[str, Dict[str, Any]]] = {
        'gpt-4': {
            'fixed_temperature': True,
            'streaming': True,
            'max_tokens': 8192
        },
        'gpt-4o': {
            'fixed_temperature': True,
            'streaming': True,
            'max_tokens': 16384,
            'supports_json_mode': True,
            'supports_vector_search': True,
            'supports_file_search': True,
            'supports_code_interpreter': True,
            'api_version': '2025-01-01-preview'
        },
        'o1': {
            'fixed_temperature': True,
            'streaming': False,
            'max_tokens': 25000,
            'supports_json_mode': True,
            'requires_reasoning_effort': True,
            'supports_vector_search': True,
            'supports_file_search': True,
            'supports_code_interpreter': True,
            'api_version': '2025-01-01-preview',
            'default_reasoning_effort': 'medium',
            'supports_completion_storage': True,
            'vector_search_config': {
                'max_chunks': 50,
                'chunk_size': 1000,
                'chunk_overlap': 100,
                'default_strictness': 3
            }
        },
        'gpt-3.5-turbo': {
            'fixed_temperature': False,
            'streaming': True,
            'max_tokens': 4096
        }
    }

    def __post_init__(self):
        """Validate and adjust fields after initialization."""
        self.id = int(self.id)
        self.provider_id = int(self.provider_id)
        self.apply_provider_constraints()


    def apply_provider_constraints(self):
        """Properly apply constraints from provider"""
        provider = Provider.get_by_id(self.provider_id)
        if not provider or not provider.capabilities:
            return

        provider_caps = provider.capabilities

        if provider_caps.get('fixed_temperature'):
            self.temperature = provider_caps['fixed_temperature']

        if 'max_tokens' in provider_caps:
            if self.max_completion_tokens:
                self.max_completion_tokens = min(
                    self.max_completion_tokens,
                    provider_caps['max_tokens']
                )

    @staticmethod
    def create(data: ModelDict) -> Optional[int]:
        """
        Create a new model record.

        Args:
            data: Dictionary containing model configuration

        Returns:
            Optional[int]: ID of created model or None if creation failed

        Raises:
            ValueError: If model configuration is invalid
        """
        try:
            with db_session() as session:
                logger.debug(
                    "Creating model with data: %s",
                    {k: v if k != "api_key" else "****" for k, v in data.items()},
                )

                # Get provider constraints
                provider = Provider.get_by_id(data["provider_id"])
                if not provider:
                    raise ValueError("Invalid provider_id")

                # Apply provider validation rules
                if provider.validation_rules.get('fixed_temperature'):
                    data["temperature"] = 1.0

                if 'max_tokens' in provider.validation_rules:
                    data["max_completion_tokens"] = min(
                        data.get("max_completion_tokens", 16384),
                        int(provider.validation_rules['max_tokens'])
                    )

                # Check for existing models with same name/deployment
                check_query = text(
                    """
                    SELECT name, deployment_name
                    FROM models
                    WHERE (LOWER(name) = LOWER(:name)
                    OR LOWER(deployment_name) = LOWER(:deployment_name))
                    AND provider_id = :provider_id
                    AND (NOT is_default OR :is_default = TRUE)
                """
                )
                existing = session.execute(
                    check_query,
                    {
                        "name": data["name"],
                        "deployment_name": data["deployment_name"],
                        "provider_id": data["provider_id"],
                        "is_default": data.get("is_default", False)
                    },
                ).fetchone()

                if existing:
                    field = (
                        "name"
                        if existing[0].lower() == data["name"].lower()
                        else "deployment_name"
                    )
                    raise ValueError(f"A model with this {field} already exists for this provider")

                # Validate configuration
                Model.validate_model_config(data)

                # Update default status if needed
                if data.get("is_default", False):
                    session.execute(
                        text("UPDATE models SET is_default = FALSE WHERE is_default = TRUE")
                    )

                # Insert new model
                query = text(
                    """
                    INSERT INTO models (
                        provider_id, name, deployment_name, description, api_endpoint, api_key,
                        api_version, temperature, max_tokens, max_completion_tokens,
                        model_type, requires_o1_handling, supports_streaming, is_default,
                        reasoning_effort, store_completion, created_at
                    ) VALUES (
                        :provider_id, :name, :deployment_name, :description, :api_endpoint, :api_key,
                        :api_version, :temperature, :max_tokens, :max_completion_tokens,
                        :model_type, :requires_o1_handling, :supports_streaming, :is_default,
                        :reasoning_effort, :store_completion, NOW()
                    )
                    RETURNING id
                """
                )
                result = session.execute(query, data)
                model_id = result.scalar()

                if model_id is None:
                    logger.error("Failed to create model - no ID returned")
                    return None

                session.commit()
                logger.info("Model created with ID: %d", model_id)
                return model_id

        except Exception as e:
            logger.error("Failed to create model: %s", e)
            raise

    @staticmethod
    def get_immutable_fields(model_id: int) -> List[str]:
        """Get list of fields that cannot be modified for an existing model.

        Args:
            model_id: ID of the model to check

        Returns:
            List[str]: Names of immutable fields
        """
        try:
            with db_session() as db:
                # Get model type
                query = text("SELECT model_type FROM models WHERE id = :id")
                model_type = db.execute(query, {"id": model_id}).scalar()

                # Default immutable fields
                immutable_fields = ["provider_id"]

                # Add model-type specific immutable fields
                if model_type == "o1-preview":
                    immutable_fields.extend([
                        "temperature",       # Fixed at 1.0
                        "supports_streaming" # Always false
                    ])

                return immutable_fields

        except Exception as e:
            logger.error(f"Error getting immutable fields for model {model_id}: {str(e)}")
            return ["provider_id"]  # Default fallback

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID from the database.

        Args:
            model_id (int): ID of the model to retrieve.

        Returns:
            Optional[Model]: An instance of the Model class if found, None otherwise.
        """
        try:
            with db_session() as session:
                # Retrieve model data
                query = text("SELECT * FROM models WHERE id = :id")
                row = session.execute(query, {"id": model_id}).mappings().first()

                if not row:
                    logger.warning("No model found with ID %d in database", model_id)
                    return None

                model_dict = dict(row)

                # Handle API key decryption using centralized utility
                from utils.encryption import decrypt_api_key, EncryptionError

                encrypted_key = model_dict.get("api_key", "")
                if encrypted_key:
                    try:
                        model_dict["api_key"] = decrypt_api_key(encrypted_key)
                    except EncryptionError as e:
                        logger.error(str(e))
                        model_dict["api_key"] = ""
                else:
                    model_dict["api_key"] = ""

                # Normalize boolean fields
                boolean_fields = ['requires_o1_handling', 'supports_streaming', 'is_default']
                for bool_field in boolean_fields:
                    value = model_dict.get(bool_field)
                    if isinstance(value, str):
                        model_dict[bool_field] = value.lower() in ('true', 't', '1')
                    elif isinstance(value, int):
                        model_dict[bool_field] = bool(value)

                return Model(**model_dict)

        except Exception as e:
            logger.error("Error retrieving model by ID %d: %s", model_id, e, exc_info=True)
            return None


    @staticmethod
    def update(model_id: int, data: Dict[str, Any]) -> None:
        """
        Update model with validated data.

        Args:
            model_id: ID of model to update
            data: Dictionary of fields to update
        """
        try:
            if not model_id:
                raise ValueError("Model ID is required")

            with db_session() as db:
                # Filter allowed fields
                allowed_fields = {
                    "name", "deployment_name", "description",
                    "api_endpoint", "api_key", "api_version",
                    "temperature", "max_tokens", "max_completion_tokens",
                    "model_type", "requires_o1_handling",
                    "supports_streaming", "is_default", "provider_id",
                    "reasoning_effort", "store_completion"
                }

                update_data = {
                    key: value for key, value in data.items()
                    if key in allowed_fields
                }

                if not update_data:
                    logger.info("No valid fields to update for model ID %d", model_id)
                    return

                # Get existing model data
                existing_model = Model.get_by_id(model_id)
                if not existing_model:
                    raise ValueError(f"Model with ID {model_id} not found")

                # Apply provider constraints
                model_type = data.get("model_type", "")
                provider_caps = Model.PROVIDER_CAPABILITIES.get(model_type, {})

                # Handle temperature constraint
                if provider_caps.get('fixed_temperature'):
                    update_data["temperature"] = 1.0

                # Handle streaming support
                update_data["supports_streaming"] = bool(
                    provider_caps.get('streaming', True)
                )

                # Handle token limits
                if "max_completion_tokens" in update_data:
                    max_tokens = provider_caps.get('max_tokens', 16384)
                    if max_tokens is not None:
                        update_data["max_completion_tokens"] = min(
                            update_data["max_completion_tokens"] or 0,
                            max_tokens
                        )

                # Handle o1-preview settings
                requires_o1_handling = update_data.get("requires_o1_handling", existing_model.requires_o1_handling)
                if requires_o1_handling:
                    # Force disable streaming for o1-preview models
                    update_data["supports_streaming"] = False
                    # Force temperature to 1.0 for o1-preview models
                    update_data["temperature"] = 1.0
                    logger.debug("Enforcing o1-preview constraints for model %d", model_id)

                # Ensure is_default is properly handled
                if "is_default" in update_data:
                    if update_data["is_default"]:
                        # Set all other models to non-default
                        db.execute(
                            text("UPDATE models SET is_default = :new_default WHERE id != :model_id"),
                            {"new_default": False, "model_id": model_id}
                        )
                    else:
                        # Ensure at least one model remains default when unsetting is_default
                        if update_data.get("is_default") is False:
                            default_count = db.execute(
                                text("SELECT COUNT(*) FROM models WHERE is_default = :current_default AND id != :model_id"),
                                {"current_default": True, "model_id": model_id}
                            ).scalar()
                            if default_count == 0:
                                raise ValueError("Cannot unset default model without setting another as default")

                # Validate configuration before update, passing current model_id
                Model.validate_model_config(update_data, model_id)

                # Get current version
                current_version = db.execute(
                    text("SELECT version FROM models WHERE id = :model_id"),
                    {"model_id": model_id}
                ).scalar()

                if current_version is None:
                    raise ValueError(f"Model with ID {model_id} not found")

                # Add version increment to update data
                update_data['version'] = current_version + 1

                # Build update query with version check
                set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
                params = cast(Dict[str, Any], {**update_data, "model_id": model_id, "current_version": current_version})

                query = text(
                    f"""
                    UPDATE models
                    SET {set_clause}
                    WHERE id = :model_id AND version = :current_version
                    RETURNING version
                """
                ).bindparams(**params)

                result = db.execute(query)
                if result.rowcount == 0:
                    raise ValueError("Model was modified by another user. Please refresh and try again.")

                # Update default status if needed
                if update_data.get("is_default", False):
                    db.execute(
                        text(
                            """
                            UPDATE models
                            SET is_default = :new_default
                            WHERE id != :model_id AND is_default = :current_default
                        """
                        ),
                        {"new_default": False, "current_default": True, "model_id": model_id},
                    )

                db.commit()
                logger.info("Model updated (ID %d)", model_id)

        except Exception as e:
            logger.error("Failed to update model %d: %s", model_id, e, exc_info=True)
            raise ValueError(f"Failed to update model: {str(e)}")

    @staticmethod
    def delete(model_id: int) -> None:
        """
        Delete a model from the database.

        Args:
            model_id: ID of the model to delete

        Raises:
            ValueError: If model is in use by chats or if it's the last default model
        """
        with db_session() as db:
            try:
                # Check if the model is the last default model
                is_default_query = text("SELECT is_default FROM models WHERE id = :model_id")
                is_default_result = db.execute(is_default_query, {"model_id": model_id}).scalar()

                if is_default_result:
                    default_count_query = text("SELECT COUNT(*) FROM models WHERE is_default = TRUE")
                    default_count = db.execute(default_count_query).scalar()
                    if default_count == 1:
                        raise ValueError("Cannot delete the last default model")

                # Check if model is in use
                check_query = text(
                    """
                    SELECT COUNT(*) as count
                    FROM chats
                    WHERE model_id = :model_id
                """
                )
                result = (
                    db.execute(check_query, {"model_id": model_id}).mappings().first()
                )
                if result and result["count"] > 0:
                    raise ValueError("Cannot delete model that is in use by chats")

                # Log the provider type before deletion
                model = Model.get_by_id(model_id)
                if model:
                    logger.info("Deleting model with provider: %s", model.model_type)

                # Delete associated versions
                delete_versions_query = text("DELETE FROM model_versions WHERE model_id = :model_id")
                db.execute(delete_versions_query, {"model_id": model_id})

                # Delete the model
                query = text("DELETE FROM models WHERE id = :model_id")
                db.execute(query, {"model_id": model_id})
                db.commit()
                logger.info("Model deleted (ID %d)", model_id)

            except Exception as e:
                db.rollback()
                logger.error("Failed to delete model %d: %s", model_id, e)
                raise

    @staticmethod
    def get_default() -> Optional["Model"]:
        """
        Retrieve the default model.
        Returns:
            Optional[Model]: Default model instance if found, None otherwise
        """
        with db_session() as db:
            try:
                query = text("SELECT * FROM models WHERE is_default = TRUE")
                result = db.execute(query).mappings().first()
                if result:
                    model_dict = dict(result)
                    # Convert numeric fields to proper types
                    model_dict["id"] = int(model_dict["id"]) if model_dict.get("id") is not None else 0
                    model_dict["provider_id"] = int(model_dict["provider_id"]) if model_dict.get("provider_id") is not None else 0
                    model_dict["temperature"] = float(model_dict["temperature"]) if model_dict.get("temperature") is not None else None
                    model_dict["max_tokens"] = int(model_dict["max_tokens"]) if model_dict.get("max_tokens") is not None else None
                    model_dict["max_completion_tokens"] = int(model_dict["max_completion_tokens"]) if model_dict.get("max_completion_tokens") is not None else 8300
                    return Model(**model_dict)
                return None
            except Exception as e:
                logger.error("Failed to retrieve default model: %s", e)
                return None

    @staticmethod
    def validate_model_config(config: ModelDict, model_id: Optional[int] = None) -> None:
        """
        Validate model configuration parameters.
        """
        # Get provider and its capabilities
        provider = Provider.get_by_id(config["provider_id"])
        if not provider:
            raise ValueError("Invalid provider_id")

        provider_caps = provider.capabilities

        # Apply provider-specific constraints
        if provider_caps.get('fixed_temperature'):
            config['temperature'] = 1.0

        config['supports_streaming'] = provider_caps.get('streaming', True)

        # Handle max_completion_tokens based on model type and provider capabilities
        model_type = config.get('model_type', '').lower()
        requires_o1 = config.get('requires_o1_handling', False)
        is_o1_preview = model_type == 'o1-preview' and requires_o1

        # Get provider-specific capabilities
        model_caps = provider_caps.get(model_type, {})

        # For o1-preview models, enforce stricter limits
        if is_o1_preview:
            max_tokens = config.get('max_completion_tokens', 8300)
            if not (1 <= max_tokens <= 25000):
                raise ValueError("For o1-preview models, max_completion_tokens must be between 1 and 25000 (OpenAI recommended)")
            config['max_completion_tokens'] = max_tokens
        else:
            # For non-o1 models (like azure), just ensure it's a positive number
            max_tokens = config.get('max_completion_tokens')
            if max_tokens is not None and max_tokens <= 0:
                raise ValueError("max_completion_tokens must be positive")

            # Use provider's max_tokens if available, otherwise no upper limit
            if 'max_tokens' in model_caps:
                config['max_completion_tokens'] = min(
                    max_tokens or model_caps['max_tokens'],
                    model_caps['max_tokens']
                )

        # Handle reasoning settings for o1/o3 models
        model_type = config.get('model_type', '').lower()
        is_reasoning_model = model_type in ['o1-preview', 'o3-mini']

        if is_reasoning_model:
            # Validate reasoning_effort
            reasoning_effort = config.get('reasoning_effort', 'medium')
            if reasoning_effort not in ['low', 'medium', 'high']:
                raise ValueError("reasoning_effort must be one of: low, medium, high")
            config['reasoning_effort'] = reasoning_effort

            # Ensure store_completion is boolean
            store_completion = config.get('store_completion', False)
            config['store_completion'] = bool(store_completion)
        else:
            # For non-reasoning models, set defaults
            config['reasoning_effort'] = 'medium'
            config['store_completion'] = False

        # Validate required fields with strict type checking
        required_fields = {
            "provider_id": (int, "Provider ID must be an integer"),
            "name": (str, "Name must be a non-empty string"),
            "deployment_name": (str, "Deployment name must be a non-empty string"),
            "model_type": (str, "Model type must be a non-empty string"),
            "api_endpoint": (str, "API endpoint must be a valid HTTPS URL"),
            "api_key": (str, "API key must be a non-empty string")
        }

        for field, (expected_type, error_msg) in required_fields.items():
            if field not in config:
                raise ValueError(f"Missing required field: {field}")

            value = config[field]
            if value is None or value == "":
                raise ValueError(error_msg)

            if not isinstance(value, expected_type):
                raise ValueError(f"{field} must be of type {expected_type.__name__}")

        # API endpoint validation using provider's rules
        api_endpoint = config["api_endpoint"]
        if not isinstance(api_endpoint, str):
            raise ValueError("API endpoint must be a string")

        # Basic HTTPS validation
        if not api_endpoint.startswith("https://"):
            raise ValueError("API endpoint must use HTTPS")

        # Get provider's validation rules
        validation_rules = provider.validation_rules
        if isinstance(validation_rules, str):
            validation_rules = json.loads(validation_rules)

        # Validate 'api_endpoint' using provider's 'endpoint' pattern
        api_endpoint = config.get("api_endpoint")
        if api_endpoint:
            pattern = validation_rules.get('endpoint')
            if pattern:
                import re
                if not re.match(pattern, api_endpoint):
                    raise ValueError("API endpoint does not match the required format specified by the provider.")

        if provider.is_azure:
            # Validate 'deployment_name' using provider's 'model_id' pattern
            deployment_name = config.get("deployment_name")
            if deployment_name:
                pattern = validation_rules.get('model_id')
                if pattern:
                    import re
                    if not re.match(pattern, deployment_name):
                        raise ValueError("Deployment name does not match the required format specified by the provider.")
        else:
            # For OpenAI provider, remove any deployment name from the config
            config.pop("deployment_name", None)

        # Validate temperature
        temperature = config.get("temperature")
        if temperature is not None and (temperature < 0 or temperature > 2):
            raise ValueError("Temperature must be between 0 and 2")

        # Validate max_tokens
        max_tokens = config.get("max_tokens")
        if max_tokens is not None and max_tokens < 1:
            raise ValueError("Max tokens must be at least 1")

        # Validate only one default model, allowing updates to current default
        if config.get('is_default', False):
            with db_session() as session:
                query = text("""
                    SELECT COUNT(*) FROM models
                    WHERE is_default = TRUE
                    AND (:model_id IS NULL OR id != :model_id)
                """)
                existing_defaults = session.execute(query, {"model_id": model_id}).scalar()
                if existing_defaults > 0 and model_id is None:
                    raise ValueError("Only one default model allowed")

    @staticmethod
    def get_all(limit: int = 10, offset: int = 0, exclude_id: Optional[int] = None) -> List["Model"]:
        """
        Retrieve all models with pagination.

        Args:
            limit: Maximum number of models to retrieve
            offset: Offset for pagination
            exclude_id: Optional ID of a model to exclude

        Returns:
            List[Model]: List of Model instances
        """
        with db_session() as session:
            try:
                query = text(
                    """
                    SELECT *
                    FROM models
                    WHERE (:exclude_id IS NULL OR id != :exclude_id)
                    ORDER BY id
                    LIMIT :limit
                    OFFSET :offset
                """
                )
                result = session.execute(
                    query, {"limit": limit, "offset": offset, "exclude_id": exclude_id}
                ).mappings().all()
                models = []
                for row in result:
                    model_dict = dict(row)
                    # Convert numeric fields to proper types
                    model_dict["id"] = int(model_dict["id"]) if model_dict.get("id") is not None else 0
                    model_dict["provider_id"] = int(model_dict["provider_id"]) if model_dict.get("provider_id") is not None else 0
                    model_dict["temperature"] = float(model_dict["temperature"]) if model_dict.get("temperature") is not None else None
                    model_dict["max_tokens"] = int(model_dict["max_tokens"]) if model_dict.get("max_tokens") is not None else None
                    model_dict["max_completion_tokens"] = int(model_dict["max_completion_tokens"]) if model_dict.get("max_completion_tokens") is not None else 8300
                    models.append(Model(**model_dict))

                for model in models:
                    provider_caps = Model.PROVIDER_CAPABILITIES.get(model.model_type, {})
                    if provider_caps.get('fixed_temperature'):
                        model.temperature = 1.0
                    model.supports_streaming = provider_caps.get('streaming', True)
                    model.max_completion_tokens = min(
                        model.max_completion_tokens,
                        provider_caps.get('max_tokens', 16384)
                    )
                return models

            except Exception as e:
                logger.error("Failed to retrieve models: %s", e)
                return []

    @staticmethod
    def set_default(model_id: int) -> None:
        """
        Set a model as the default.

        Args:
            model_id: ID of the model to set as default

        Raises:
            ValueError: If model not found
        """
        with db_session() as session:
            try:
                # Check if the model exists
                model = Model.get_by_id(model_id)
                if not model:
                    raise ValueError(f"Model with ID {model_id} not found")

                provider_caps = Model.PROVIDER_CAPABILITIES.get(model.model_type, {})
                if provider_caps.get('fixed_temperature'):
                    model.temperature = 1.0
                model.supports_streaming = bool(provider_caps.get('streaming', True))
                model.max_completion_tokens = min(
                    model.max_completion_tokens,
                    provider_caps.get('max_tokens', 16384) or model.max_completion_tokens
                )

                # Set all other models to non-default
                session.execute(
                    text("UPDATE models SET is_default = FALSE WHERE id != :model_id"),
                    {"model_id": model_id},
                )

                # Set the specified model to default
                session.execute(
                    text("UPDATE models SET is_default = TRUE WHERE id = :model_id"),
                    {"model_id": model_id},
                )

                session.commit()
                logger.info("Model %d set as default", model_id)

            except Exception as e:
                session.rollback()
                logger.error("Failed to set model %d as default: %s", model_id, e)
                raise
