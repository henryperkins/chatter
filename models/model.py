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
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, cast
from cryptography.fernet import Fernet, InvalidToken

from sqlalchemy import text

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
        version: Model configuration version
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
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = 8300
    is_default: bool = False
    requires_o1_handling: bool = False
    supports_streaming: bool = False
    api_version: str = "2023-07-01-preview"
    version: int = 1
    created_at: Optional[str] = None

    # Add provider capability constants
    PROVIDER_CAPABILITIES = {
        'o1-preview': {
            'fixed_temperature': True,
            'streaming': False,
            'max_tokens': 8300,
            'token_overhead': 3
        },
        'azure': {
            'fixed_temperature': False,
            'streaming': True,
            'max_tokens': 16384,
            'token_overhead': 3
        }
    }

    def __post_init__(self):
        """Validate and adjust fields after initialization."""
        self.id = int(self.id)
        self.provider_id = int(self.provider_id)

    def get_provider_capabilities(self) -> Dict[str, Any]:
        """Get capabilities for the current model's provider"""
        return self.PROVIDER_CAPABILITIES.get(self.model_type, {})

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

                # Get model type safely
                model_type = str(data.get("model_type", "")) if "model_type" in data else ""
                # Apply provider constraints before creation
                provider_caps = Model.PROVIDER_CAPABILITIES.get(model_type, {})
                if provider_caps.get('fixed_temperature'):
                    data["temperature"] = 1.0
                data["supports_streaming"] = bool(provider_caps.get('streaming', True))
                if "max_completion_tokens" in data:
                    max_tokens = int(provider_caps.get('max_tokens', 16384))
                    comp_tokens = int(data["max_completion_tokens"]) if data["max_completion_tokens"] is not None else max_tokens
                    data["max_completion_tokens"] = min(comp_tokens, max_tokens)

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

                # Handle version auto-increment
                if not data.get('version'):
                    # Get the current maximum version number for this model
                    max_version = (
                        session.execute(
                            text("SELECT MAX(version) FROM models WHERE name = :name AND provider_id = :provider_id"),
                            {"name": data["name"], "provider_id": data["provider_id"]}
                        ).scalar() or 0
                    )
                    data['version'] = max_version + 1

                # Insert new model
                query = text(
                    """
                    INSERT INTO models (
                        provider_id, name, deployment_name, description, api_endpoint, api_key,
                        api_version, temperature, max_tokens, max_completion_tokens,
                        model_type, requires_o1_handling, supports_streaming, is_default, version,
                        created_at
                    ) VALUES (
                        :provider_id, :name, :deployment_name, :description, :api_endpoint, :api_key,
                        :api_version, :temperature, :max_tokens, :max_completion_tokens,
                        :model_type, :requires_o1_handling, :supports_streaming, :is_default, :version,
                        NOW()
                    )
                    RETURNING id
                """
                )
                result = session.execute(query, data)
                model_id = result.scalar()

                if model_id is None:
                    logger.error("Failed to create model - no ID returned")
                    return None

                # Create initial version
                Model.create_version(model_id, data)

                session.commit()
                logger.info("Model created with ID: %d", model_id)
                return model_id

        except Exception as e:
            logger.error("Failed to create model: %s", e)
            raise

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.

        Args:
            model_id: ID of the model to retrieve

        Returns:
            Optional[Model]: Model instance if found, None otherwise

        Raises:
            ValueError: If there's an error retrieving the model
        """
        try:
            with db_session() as session:
                query = text("SELECT * FROM models WHERE id = :id")
                row = session.execute(query, {"id": model_id}).mappings().first()

                if not row:
                    logger.warning("No model found with ID %d in database", model_id)
                    return None

                model_dict = dict(row)

                # Handle API key decryption
                key = Config.ENCRYPTION_KEY
                if not key:
                    logger.error("Encryption key not configured in application settings")
                    raise ValueError("Encryption key not configured")

                try:
                    # Ensure key is bytes
                    if isinstance(key, str):
                        key = key.encode()

                    # Initialize cipher suite
                    cipher_suite = Fernet(key)

                    # Handle empty or invalid API key
                    encrypted_key = model_dict.get("api_key", "")
                    if not encrypted_key:
                        logger.warning("No API key found for model %d", model_id)
                        model_dict["api_key"] = ""
                    else:
                        # Decrypt the API key
                        if isinstance(encrypted_key, str):
                            encrypted_key = encrypted_key.encode()
                        model_dict["api_key"] = cipher_suite.decrypt(encrypted_key).decode()

                except InvalidToken as e:
                    logger.error(
                        "Failed to decrypt API key for model %d. "
                        "Encryption key mismatch or corrupted data. Error: %s",
                        model_id,
                        str(e)
                    )
                    # Raise an exception instead of returning None
                    raise ValueError("Failed to decrypt API key. Encryption key may be incorrect.")
                except Exception as e:
                    logger.error(
                        "Unexpected error decrypting API key for model %d: %s",
                        model_id,
                        str(e)
                    )
                    # Raise the exception to allow it to be handled by the calling code
                    raise

                # Log safely (excluding sensitive data)
                safe_dict = {k: v for k, v in model_dict.items() if k != "api_key"}
                logger.debug("Successfully retrieved model by ID %d: %s", model_id, safe_dict)

                # Helper function to convert to boolean
                def to_bool(value):
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        return value.lower() in ('true', 't', '1')
                    if isinstance(value, int):
                        return value == 1
                    return False

                # Convert boolean fields to proper booleans
                model_dict['requires_o1_handling'] = to_bool(model_dict.get('requires_o1_handling'))
                model_dict['supports_streaming'] = to_bool(model_dict.get('supports_streaming'))
                model_dict['is_default'] = to_bool(model_dict.get('is_default'))

                # Create and return the model instance
                model = Model(**model_dict)

                # Apply provider constraints
                if model:
                    provider_caps = Model.PROVIDER_CAPABILITIES.get(model.model_type, {})
                    if provider_caps.get('fixed_temperature'):
                        model.temperature = 1.0
                    model.supports_streaming = bool(provider_caps.get('streaming', True))
                    model.max_completion_tokens = min(
                        model.max_completion_tokens,
                        provider_caps.get('max_tokens', 16384) or model.max_completion_tokens
                    )

                # Validate the model configuration
                required_attrs = [
                    "provider_id",
                    "deployment_name",
                    "api_endpoint",
                    "api_key",
                    "max_completion_tokens",
                    "model_type",
                    "api_version"
                ]

                for attr in required_attrs:
                    if not hasattr(model, attr) or not getattr(model, attr):
                        logger.error(f"Model {model_id} missing required attribute: {attr}")
                        return None

                return model

        except Exception as e:
            logger.error("Error retrieving model by ID %d: %s", model_id, e, exc_info=True)
            return None

    @staticmethod
    def update(model_id: int, data: ModelDict) -> None:
        """
        Update an existing model's attributes.

        Args:
            model_id: ID of the model to update
            data: Dictionary containing updated model configuration

        Raises:
            ValueError: If model not found or configuration invalid
        """
        with db_session() as db:
            try:
                # Get existing model to check current state
                model = Model.get_by_id(model_id)
                if not model:
                    raise ValueError(f"Model with ID {model_id} not found")

                # Filter allowed fields
                allowed_fields = {
                    "name",
                    "deployment_name",
                    "description",
                    "api_endpoint",
                    "api_key",
                    "api_version",
                    "temperature",
                    "max_tokens",
                    "max_completion_tokens",
                    "model_type",
                    "requires_o1_handling",
                    "supports_streaming",
                    "is_default",
                    "version",
                    "provider_id"  # Allow provider_id updates
                }
                update_data = {
                    key: value for key, value in data.items() if key in allowed_fields
                }

                if not update_data:
                    logger.info("No valid fields to update for model ID %d", model_id)
                    return

                # Apply provider constraints before update
                provider_caps = Model.PROVIDER_CAPABILITIES.get(data.get("model_type"), {})
                if provider_caps.get('fixed_temperature'):
                    data["temperature"] = 1.0
                data["supports_streaming"] = provider_caps.get('streaming', True)
                if "max_completion_tokens" in data:
                    data["max_completion_tokens"] = min(
                        data["max_completion_tokens"],
                        provider_caps.get('max_tokens', 16384)
                    )

                # Handle o1-preview settings
                if update_data.get("requires_o1_handling", False) or model.requires_o1_handling:
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

                # Validate configuration before update
                Model.validate_model_config(update_data)

                # Handle version auto-increment
                if 'version' not in update_data or update_data.get('version') is None:
                    # Get the current version number and increment
                    current_version = (
                        db.execute(
                            text("SELECT version FROM models WHERE id = :model_id"),
                            {"model_id": model_id}
                        ).scalar() or 0
                    )
                    update_data['version'] = current_version + 1
                else:
                    update_data['version'] += 1

                # Build update query
                set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
                params = cast(Dict[str, Any], {**update_data, "model_id": model_id})

                query = text(
                    f"""
                    UPDATE models
                    SET {set_clause}
                    WHERE id = :model_id
                """
                ).bindparams(**params)

                db.execute(query)

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

                # Increment version and create new version
                if 'version' in update_data:
                    update_data['version'] += 1
                else:
                    update_data['version'] = 1
                Model.create_version(model_id, update_data)

                db.commit()
                logger.info("Model updated (ID %d)", model_id)

            except Exception as e:
                db.rollback()
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
    def create_default_model() -> None:
        """Create a default model configuration."""
        # Get the Azure provider ID
        with db_session() as session:
            provider = session.execute(
                text("SELECT id FROM providers WHERE slug = 'azure' LIMIT 1")
            ).scalar()
            if not provider:
                raise ValueError("Azure provider not found")

        default_model_data = {
            "provider_id": provider,
            "name": Config.DEFAULT_MODEL_NAME,
            "deployment_name": Config.DEFAULT_DEPLOYMENT_NAME,
            "description": Config.DEFAULT_MODEL_DESCRIPTION,
            "api_endpoint": Config.DEFAULT_API_ENDPOINT,
            "api_key": Config.AZURE_API_KEY,
            "temperature": Config.DEFAULT_TEMPERATURE,
            "max_tokens": Config.DEFAULT_MAX_TOKENS,
            "max_completion_tokens": Config.DEFAULT_MAX_COMPLETION_TOKENS,
            "model_type": "azure",
            "api_version": "2023-07-01-preview",
            "requires_o1_handling": Config.DEFAULT_REQUIRES_O1_HANDLING,
            "supports_streaming": Config.DEFAULT_SUPPORTS_STREAMING,
            "is_default": True,
            "version": 1,
        }

        # Apply provider constraints for the default model
        provider_caps = Model.PROVIDER_CAPABILITIES.get(default_model_data.get("model_type"), {})
        if provider_caps.get('fixed_temperature'):
            default_model_data["temperature"] = 1.0
        default_model_data["supports_streaming"] = provider_caps.get('streaming', True)
        if "max_completion_tokens" in default_model_data:
            default_model_data["max_completion_tokens"] = min(default_model_data["max_completion_tokens"] or provider_caps.get('max_tokens', 16384),
                default_model_data["max_completion_tokens"],
                provider_caps.get('max_tokens', 16384)
            )

        Model.create(default_model_data)

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
    def validate_model_config(config: ModelDict) -> None:
        """
        Validate model configuration parameters.
        """
        # Apply provider-specific configurations
        provider_caps = Model.PROVIDER_CAPABILITIES.get(config['model_type'], {})

        # Apply provider-specific constraints
        if provider_caps.get('fixed_temperature'):
            config['temperature'] = 1.0

        config['supports_streaming'] = provider_caps.get('streaming', True)
        config['max_completion_tokens'] = min(
            config.get('max_completion_tokens', 16384),
            provider_caps.get('max_tokens', 16384)
        )

        # Continue with existing validation logic...
        # Example: Check if required fields are present
        required_fields = [
            "provider_id",
            "name",
            "deployment_name",
            "model_type",
            "api_endpoint",
            "api_key"
        ]
        for field in required_fields:
            if field not in config or not config[field]:
                raise ValueError(f"Missing required field: {field}")

        # Validate temperature
        temperature = config.get("temperature")
        if temperature is not None and (temperature < 0 or temperature > 2):
            raise ValueError("Temperature must be between 0 and 2")

        # Validate max_tokens
        max_tokens = config.get("max_tokens")
        if max_tokens is not None and max_tokens < 1:
            raise ValueError("Max tokens must be at least 1")

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

    @staticmethod
    def get_version_history(model_id: int, limit: int = 10, offset: int = 0) -> List[ModelDict]:
        """
        Get version history for a model.

        Args:
            model_id: ID of the model
            limit: Maximum number of versions to retrieve
            offset: Offset for pagination

        Returns:
            List[ModelDict]: List of model version dictionaries
        """
        with db_session() as session:
            try:
                query = text(
                    """
                    SELECT mv.*
                    FROM model_versions mv
                    JOIN models m ON mv.model_id = m.id
                    WHERE mv.model_id = :model_id
                    ORDER BY mv.version DESC
                    LIMIT :limit
                    OFFSET :offset
                """
                )
                versions = session.execute(
                    query, {"model_id": model_id, "limit": limit, "offset": offset}
                ).mappings().all()

                version_dicts = []
                for version in versions:
                    version_dict = dict(version)
                    provider_caps = Model.PROVIDER_CAPABILITIES.get(version_dict.get("model_type"), {})

                    if provider_caps.get('fixed_temperature'):
                        version_dict["temperature"] = 1.0
                    version_dict["supports_streaming"] = provider_caps.get('streaming', True)

                    if "max_completion_tokens" in version_dict:
                        version_dict["max_completion_tokens"] = min(
                            version_dict["max_completion_tokens"],
                            provider_caps.get('max_tokens', 16384)
                        )
                    version_dicts.append(version_dict)

                return version_dicts

            except Exception as e:
                logger.error("Failed to retrieve version history for model %d: %s", model_id, e)
                return []

    @staticmethod
    def revert_to_version(model_id: int, version: int) -> None:
        """
        Revert a model to a previous version.

        Args:
            model_id: ID of the model
            version: Version number to revert to

        Raises:
            ValueError: If model or version not found
        """
        with db_session() as session:
            try:
                # Retrieve the version data
                version_data = Model.get_version_data(model_id, version)
                if not version_data:
                    raise ValueError(f"Version {version} not found for model {model_id}")

                # Apply provider constraints
                provider_caps = Model.PROVIDER_CAPABILITIES.get(version_data.get("model_type"), {})
                if provider_caps.get('fixed_temperature'):
                    version_data["temperature"] = 1.0
                version_data["supports_streaming"] = provider_caps.get('streaming', True)
                if "max_completion_tokens" in version_data:
                    version_data["max_completion_tokens"] = min(version_data["max_completion_tokens"] or provider_caps.get('max_tokens', 16384),
                        version_data["max_completion_tokens"],
                        provider_caps.get('max_tokens', 16384)
                    )

                # Remove the ID and version from the version data (as it's an update)
                version_data.pop("id", None)
                version_data.pop("version", None)
                version_data.pop("created_at", None)

                # Update the model with the version data
                Model.update(model_id, version_data)

            except Exception as e:
                logger.error(
                    "Failed to revert model %d to version %d: %s", model_id, version, e
                )
                raise

    @staticmethod
    def create_version(model_id: int, data: ModelDict) -> None:
        """
        Create a new version record for a model.

        Args:
            model_id: ID of the model
            data: Model data to create the version from
        """
        with db_session() as session:
            try:
                # Ensure the model exists
                model_query = text("SELECT 1 FROM models WHERE id = :model_id")
                model_exists = session.execute(model_query, {"model_id": model_id}).scalar()
                if not model_exists:
                    raise ValueError(f"Model with ID {model_id} not found")

                # Get the current maximum version for the model
                max_version_query = text(
                    "SELECT MAX(version) FROM model_versions WHERE model_id = :model_id"
                )
                max_version = session.execute(
                    max_version_query, {"model_id": model_id}
                ).scalar() or 0
                new_version = max_version + 1

                # Prepare the data for insertion
                insert_data = data.copy()
                insert_data["model_id"] = model_id
                insert_data["version"] = new_version

                # Construct and execute the insert query
                columns = ", ".join(insert_data.keys())
                placeholders = ", ".join(f":{key}" for key in insert_data.keys())
                insert_query = text(
                    f"""
                    INSERT INTO model_versions ({columns})
                    VALUES ({placeholders})
                """
                )
                session.execute(insert_query, insert_data)
                session.commit()
                logger.info(
                    "Created version %d for model %d", new_version, model_id
                )

            except Exception as e:
                session.rollback()
                logger.error(
                    "Failed to create version for model %d: %s", model_id, e
                )
                raise

    @staticmethod
    def get_version_data(model_id: int, version: int) -> Optional[ModelDict]:
        """
        Retrieve data for a specific model version.

        Args:
            model_id: ID of the model
            version: Version number

        Returns:
            Optional[ModelDict]: Model version data if found, None otherwise
        """
        with db_session() as session:
            try:
                query = text(
                    """
                    SELECT *
                    FROM model_versions
                    WHERE model_id = :model_id AND version = :version
                """
                )
                result = session.execute(
                    query, {"model_id": model_id, "version": version}
                ).mappings().first()

                if result:
                    return dict(result)
                return None

            except Exception as e:
                logger.error(
                    "Failed to retrieve version data for model %d, version %d: %s",
                    model_id,
                    version,
                    e,
                )
                return None

