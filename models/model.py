"""
Module for handling model operations.

This module provides a Model class for managing AI model configurations, including:
- CRUD operations for model records
- Model validation and configuration
- Version control and history tracking
- Default model management
"""

import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, ClassVar
from sqlalchemy import text, Integer, Float, Boolean, String, DateTime
from sqlalchemy.orm import mapped_column

from database import db_session
from config import Config
from logging_config import get_logger
from .provider import Provider

# Use the standardized logger
logger = get_logger(__name__)

# Type alias for clarity
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
        reasoning_effort: Reasoning effort setting for some models
        created_at: Creation timestamp
        version: Record version for optimistic locking
    """

    id: int
    provider_id: int
    name: str
    deployment_name: str
    description: str
    model_type: str
    api_endpoint: str
    api_key: str
    temperature: Optional[float] = field(
        default=None, metadata={"sa": mapped_column(Float, nullable=True)}
    )
    max_tokens: Optional[int] = field(
        default=None, metadata={"sa": mapped_column(Integer, nullable=True)}
    )
    max_completion_tokens: Optional[int] = field(
        default=8300, metadata={"sa": mapped_column(Integer, nullable=False)}
    )
    is_default: bool = field(
        default=False, metadata={"sa": mapped_column(Boolean, nullable=False)}
    )
    requires_o1_handling: bool = field(
        default=False, metadata={"sa": mapped_column(Boolean, nullable=False)}
    )
    supports_streaming: bool = field(
        default=False, metadata={"sa": mapped_column(Boolean, nullable=False)}
    )
    api_version: str = field(
        default="2024-12-01-preview",
        metadata={"sa": mapped_column(String(50), nullable=False)},
    )
    reasoning_effort: str = field(
        default="medium", metadata={"sa": mapped_column(String(10), nullable=False)}
    )
    created_at: Optional[str] = field(
        default=None, metadata={"sa": mapped_column(DateTime, nullable=True)}
    )
    version: int = field(
        default=1,
        metadata={
            "sa": mapped_column(Integer, nullable=False, server_default=text("1"))
        },
    )

    # Class-level provider capabilities – may be superseded by centralized configuration
    PROVIDER_CAPABILITIES: ClassVar[Dict[str, Dict[str, Any]]] = {
        "gpt-4": {"fixed_temperature": True, "streaming": True, "max_tokens": 8192},
        "gpt-4o": {
            "fixed_temperature": True,
            "streaming": True,
            "max_tokens": 16384,
            "supports_json_mode": True,
            "supports_vector_search": True,
            "supports_file_search": True,
            "supports_code_interpreter": True,
            "api_version": "2025-01-01-preview",
        },
        "o3-mini": {
            "fixed_temperature": True,
            "streaming": True,
            "max_tokens": 200000,
            "max_completion_tokens": 100000,
            "supports_json_mode": True,
            "requires_reasoning_effort": True,
            "api_version": "2025-01-01-preview",
            "default_reasoning_effort": "medium",
        },
        "o1": {
            "fixed_temperature": True,
            "streaming": True,
            "max_tokens": 200000,
            "max_completion_tokens": 100000,
            "supports_json_mode": True,
            "requires_reasoning_effort": True,
            "supports_vision": True,
            "api_version": "2025-01-01-preview",
            "default_reasoning_effort": "medium",
        },
        "o1-mini": {
            "fixed_temperature": True,
            "streaming": True,
            "max_tokens": 128000,
            "max_completion_tokens": 65536,
            "supports_json_mode": True,
            "requires_reasoning_effort": True,
            "api_version": "2024-12-01-preview",
            "default_reasoning_effort": "medium",
        },
        "gpt-3.5-turbo": {
            "fixed_temperature": False,
            "streaming": True,
            "max_tokens": 4096,
        },
    }

    def __post_init__(self):
        """Validate and adjust fields after initialization."""
        self.id = int(self.id)
        self.provider_id = int(self.provider_id)
        self.apply_provider_constraints()

    def apply_provider_constraints(self):
        """Apply provider constraints to model configuration."""
        provider = Provider.get_by_id(self.provider_id)
        if not provider or not provider.capabilities:
            return
        provider_caps = provider.capabilities
        if provider_caps.get("fixed_temperature"):
            self.temperature = provider_caps["fixed_temperature"]
        if "max_tokens" in provider_caps and self.max_completion_tokens:
            self.max_completion_tokens = min(
                self.max_completion_tokens, provider_caps["max_tokens"]
            )

    @staticmethod
    def get_all() -> List["Model"]:
        """
        Retrieve all models from the database.

        Returns:
            List[Model]: List of all model instances
        """
        try:
            config = Config()  # Instantiate Config class
            with db_session() as db:
                query = text("SELECT * FROM models ORDER BY name")
                results = db.execute(query).mappings().all()
                models = []
                for row in results:
                    model_dict = dict(row)
                    # Remove store_completion if present (handling database migration period)
                    model_dict.pop("store_completion", None)
                    # Normalize numeric fields
                    model_dict["id"] = int(model_dict["id"]) if model_dict.get("id") is not None else 0
                    model_dict["provider_id"] = int(model_dict["provider_id"]) if model_dict.get("provider_id") is not None else 0
                    model_dict["temperature"] = float(model_dict["temperature"]) if model_dict.get("temperature") is not None else None
                    model_dict["max_tokens"] = int(model_dict["max_tokens"]) if model_dict.get("max_tokens") is not None else None
                    model_dict["max_completion_tokens"] = int(model_dict["max_completion_tokens"]) if model_dict.get("max_completion_tokens") is not None else 8300

                    # Normalize boolean fields
                    for bool_field in ["requires_o1_handling", "supports_streaming", "is_default"]:
                        value = model_dict.get(bool_field)
                        if isinstance(value, str):
                            model_dict[bool_field] = value.lower() in ("true", "t", "1")
                        elif isinstance(value, int):
                            model_dict[bool_field] = bool(value)
                    # Decrypt API key if present
                    from utils.encryption import decrypt_api_key, EncryptionError
                    encrypted_key = model_dict.get("api_key", "")
                    if encrypted_key and config.ENCRYPTION_KEY:
                        try:
                            model_dict["api_key"] = decrypt_api_key(encrypted_key, config.ENCRYPTION_KEY)
                        except EncryptionError as e:
                            logger.error("Failed to decrypt API key for model %d: %s", model_dict["id"], str(e))
                            model_dict["api_key"] = ""
                    else:
                        model_dict["api_key"] = ""
                        logger.warning("API key not decrypted because ENCRYPTION_KEY or api_key is empty.")

                    models.append(Model(**model_dict))
                return models
        except Exception as e:
            logger.error("Error retrieving all models: %s", e, exc_info=True)
            return []

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

                # Encrypt API key before storing
                from utils.encryption import encrypt_api_key
                config = Config()
                if "api_key" in data:
                    try:
                        data["api_key"] = encrypt_api_key(data["api_key"], config.ENCRYPTION_KEY)
                    except Exception as e:
                        logger.error("Failed to encrypt API key: %s", str(e))
                        raise ValueError(f"Failed to encrypt API key: {str(e)}")

                provider = Provider.get_by_id(data["provider_id"])
                if not provider:
                    raise ValueError("Invalid provider_id")

                # Apply provider validation rules if defined
                if provider.validation_rules.get("fixed_temperature"):
                    data["temperature"] = 1.0

                if "max_tokens" in provider.validation_rules:
                    data["max_completion_tokens"] = min(
                        data.get("max_completion_tokens", 16384),
                        int(provider.validation_rules["max_tokens"]),
                    )

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
                        "is_default": data.get("is_default", False),
                    },
                ).fetchone()

                if existing:
                    field = (
                        "name"
                        if existing[0].lower() == data["name"].lower()
                        else "deployment_name"
                    )
                    raise ValueError(
                        f"A model with this {field} already exists for this provider"
                    )

                # Validate configuration using the static method
                Model.validate_model_config(data)

                if data.get("is_default", False):
                    session.execute(
                        text(
                            "UPDATE models SET is_default = FALSE WHERE is_default = TRUE"
                        )
                    )

                query = text(
                    """
                    INSERT INTO models (
                        provider_id, name, deployment_name, description, api_endpoint, api_key,
                        api_version, temperature, max_tokens, max_completion_tokens,
                        model_type, requires_o1_handling, supports_streaming, is_default,
                        created_at
                    ) VALUES (
                        :provider_id, :name, :deployment_name, :description, :api_endpoint, :api_key,
                        :api_version, :temperature, :max_tokens, :max_completion_tokens,
                        :model_type, :requires_o1_handling, :supports_streaming, :is_default,
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

                session.commit()
                logger.info("Model created with ID: %d", model_id)
                return model_id

        except Exception as e:
            logger.error("Failed to create model: %s", e)
            raise

    @staticmethod
    def get_immutable_fields(model_id: int) -> List[str]:
        """Retrieve a list of fields that cannot be modified for an existing model."""
        try:
            with db_session() as db:
                query = text("SELECT model_type FROM models WHERE id = :id")
                model_type = db.execute(query, {"id": model_id}).scalar()
                immutable_fields = ["provider_id"]
                if model_type == "o1-preview":
                    immutable_fields.extend(["temperature", "supports_streaming"])
                return immutable_fields
        except Exception as e:
            logger.error(
                "Error getting immutable fields for model %d: %s", model_id, str(e)
            )
            return ["provider_id"]

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.

        Args:
            model_id (int): ID of the model to retrieve.

        Returns:
            Optional[Model]: An instance of Model if found, otherwise None.
        """
        try:
            config = Config()  # Instantiate Config class
            with db_session() as session:
                query = text("SELECT * FROM models WHERE id = :id")
                row = session.execute(query, {"id": model_id}).mappings().first()
                if not row:
                    logger.warning("No model found with ID %d", model_id)
                    return None
                model_dict = dict(row)
                # Remove store_completion if present (handling database migration period)
                model_dict.pop("store_completion", None)

                # Decrypt API key using centralized encryption utilities
                from utils.encryption import decrypt_api_key, EncryptionError

                encrypted_key = model_dict.get("api_key", "")
                if encrypted_key:
                    try:
                        model_dict["api_key"] = decrypt_api_key(
                            encrypted_key, config.ENCRYPTION_KEY
                        )
                    except EncryptionError as e:
                        logger.error(
                            "Failed to decrypt API key for model %d: %s",
                            model_id,
                            str(e),
                        )
                        model_dict["api_key"] = ""
                else:
                    model_dict["api_key"] = ""

                # Normalize boolean fields
                for bool_field in [
                    "requires_o1_handling",
                    "supports_streaming",
                    "is_default"
                ]:
                    value = model_dict.get(bool_field)
                    if isinstance(value, str):
                        model_dict[bool_field] = value.lower() in ("true", "t", "1")
                    elif isinstance(value, int):
                        model_dict[bool_field] = bool(value)
                return Model(**model_dict)

        except Exception as e:
            logger.error(
                "Error retrieving model by ID %d: %s", model_id, e, exc_info=True
            )
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
                    "provider_id",
                    "reasoning_effort",
                }
                update_data = {
                    key: value for key, value in data.items() if key in allowed_fields
                }
                if not update_data:
                    logger.info("No valid fields to update for model ID %d", model_id)
                    return
                
                # Encrypt API key if it's being updated
                if "api_key" in update_data:
                    from utils.encryption import encrypt_api_key
                    config = Config()
                    try:
                        update_data["api_key"] = encrypt_api_key(update_data["api_key"], config.ENCRYPTION_KEY)
                    except Exception as e:
                        logger.error("Failed to encrypt API key: %s", str(e))
                        raise ValueError(f"Failed to encrypt API key: {str(e)}")

                existing_model = Model.get_by_id(model_id)
                if not existing_model:
                    raise ValueError(f"Model with ID {model_id} not found")

                provider_caps = Model.PROVIDER_CAPABILITIES.get(
                    data.get("model_type", ""), {}
                )
                if provider_caps.get("fixed_temperature"):
                    update_data["temperature"] = 1.0
                update_data["supports_streaming"] = bool(
                    provider_caps.get("streaming", True)
                )
                if "max_completion_tokens" in update_data:
                    max_tokens = provider_caps.get("max_tokens", 16384)
                    update_data["max_completion_tokens"] = min(
                        update_data["max_completion_tokens"] or 0, max_tokens
                    )
                if update_data.get(
                    "requires_o1_handling", existing_model.requires_o1_handling
                ):
                    update_data["supports_streaming"] = False
                    update_data["temperature"] = 1.0
                    logger.debug(
                        "Enforcing o1-preview constraints for model %d", model_id
                    )

                if "is_default" in update_data:
                    if update_data["is_default"]:
                        db.execute(
                            text(
                                "UPDATE models SET is_default = :new_default WHERE id != :model_id"
                            ),
                            {"new_default": False, "model_id": model_id},
                        )
                    else:
                        default_count = db.execute(
                            text(
                                "SELECT COUNT(*) FROM models WHERE is_default = :current_default AND id != :model_id"
                            ),
                            {"current_default": True, "model_id": model_id},
                        ).scalar()
                        if default_count == 0:
                            raise ValueError(
                                "Cannot unset default model without setting another as default"
                            )

                Model.validate_model_config(update_data, model_id)

                current_version = db.execute(
                    text("SELECT version FROM models WHERE id = :model_id"),
                    {"model_id": model_id},
                ).scalar()
                if current_version is None:
                    raise ValueError(f"Model with ID {model_id} not found")
                update_data["version"] = current_version + 1

                set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
                params = {
                    **update_data,
                    "model_id": model_id,
                    "current_version": current_version,
                }
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
                    raise ValueError(
                        "Model was modified by another user. Please refresh and try again."
                    )

                if update_data.get("is_default", False):
                    db.execute(
                        text(
                            """
                            UPDATE models
                            SET is_default = :new_default
                            WHERE id != :model_id AND is_default = :current_default
                            """
                        ),
                        {
                            "new_default": False,
                            "current_default": True,
                            "model_id": model_id,
                        },
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
                is_default_query = text(
                    "SELECT is_default FROM models WHERE id = :model_id"
                )
                is_default_result = db.execute(
                    is_default_query, {"model_id": model_id}
                ).scalar()
                if is_default_result:
                    default_count_query = text(
                        "SELECT COUNT(*) FROM models WHERE is_default = TRUE"
                    )
                    default_count = db.execute(default_count_query).scalar()
                    if default_count == 1:
                        raise ValueError("Cannot delete the last default model")
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
                model = Model.get_by_id(model_id)
                if model:
                    logger.info("Deleting model with provider: %s", model.model_type)
                delete_versions_query = text(
                    "DELETE FROM model_versions WHERE model_id = :model_id"
                )
                db.execute(delete_versions_query, {"model_id": model_id})
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
                    model_dict["id"] = (
                        int(model_dict["id"]) if model_dict.get("id") is not None else 0
                    )
                    model_dict["provider_id"] = (
                        int(model_dict["provider_id"])
                        if model_dict.get("provider_id") is not None
                        else 0
                    )
                    model_dict["temperature"] = (
                        float(model_dict["temperature"])
                        if model_dict.get("temperature") is not None
                        else None
                    )
                    model_dict["max_tokens"] = (
                        int(model_dict["max_tokens"])
                        if model_dict.get("max_tokens") is not None
                        else None
                    )
                    model_dict["max_completion_tokens"] = (
                        int(model_dict["max_completion_tokens"])
                        if model_dict.get("max_completion_tokens") is not None
                        else 8300
                    )
                    return Model(**model_dict)
                return None
            except Exception as e:
                logger.error("Failed to retrieve default model: %s", e)
                return None

    @staticmethod
    def validate_model_config(
        config: ModelDict, model_id: Optional[int] = None
    ) -> None:
        """
        Validate model configuration parameters.
        """
        provider = Provider.get_by_id(config["provider_id"])
        if not provider:
            raise ValueError("Invalid provider_id")
        provider_caps = provider.capabilities
        if provider_caps.get("fixed_temperature"):
            config["temperature"] = 1.0
        config["supports_streaming"] = provider_caps.get("streaming", True)
        model_type = config.get("model_type", "").lower()
        requires_o1 = config.get("requires_o1_handling", False)
        is_o1_preview = model_type == "o1-preview" and requires_o1
        model_caps = provider_caps.get(model_type, {})
        if is_o1_preview:
            max_tokens = config.get("max_completion_tokens", 8300)
            if not (1 <= max_tokens <= 25000):
                raise ValueError(
                    "For o1-preview models, max_completion_tokens must be between 1 and 25000 (OpenAI recommended)"
                )
            config["max_completion_tokens"] = max_tokens
        else:
            max_tokens = config.get("max_completion_tokens")
            if max_tokens is not None and max_tokens <= 0:
                raise ValueError("max_completion_tokens must be positive")
            if "max_tokens" in model_caps:
                config["max_completion_tokens"] = min(
                    max_tokens or model_caps["max_tokens"], model_caps["max_tokens"]
                )
        # Handle o-series model validation
        is_o_series = model_type.startswith("o")
        if is_o_series:
            # Validate reasoning effort
            reasoning_effort = config.get("reasoning_effort", "medium")
            if reasoning_effort not in ["low", "medium", "high"]:
                raise ValueError("reasoning_effort must be one of: low, medium, high")
            config["reasoning_effort"] = reasoning_effort
            # Validate max completion tokens
            max_completion_tokens = config.get("max_completion_tokens")
            model_caps = Model.PROVIDER_CAPABILITIES.get(model_type, {})
            if max_completion_tokens is not None:
                max_allowed = model_caps.get("max_completion_tokens", 100000)
                if not (1 <= max_completion_tokens <= max_allowed):
                    raise ValueError(f"max_completion_tokens must be between 1 and {max_allowed} for {model_type}")
                config["max_completion_tokens"] = max_completion_tokens

            # Force temperature to 1.0 and remove unsupported parameters
            config["temperature"] = 1.0
            config["max_tokens"] = model_caps.get("max_tokens", 200000)  # Set max_tokens from model capabilities
            config.pop("top_p", None)
            config.pop("frequency_penalty", None)
            config.pop("presence_penalty", None)
        else:
            config["reasoning_effort"] = "medium"
            config["max_tokens"] = config.get("max_tokens", 16384)  # Default for non-o-series models
        required_fields = {
            "provider_id": (int, "Provider ID must be an integer"),
            "name": (str, "Name must be a non-empty string"),
            "deployment_name": (str, "Deployment name must be a non-empty string"),
            "model_type": (str, "Model type must be a non-empty string"),
            "api_endpoint": (str, "API endpoint must be a valid HTTPS URL"),
            "api_key": (str, "API key must be a non-empty string"),
        }
        for field_name, (expected_type, error_msg) in required_fields.items():
            if field_name not in config:
                raise ValueError(f"Missing required field: {field_name}")
            value = config[field_name]
            if value is None or value == "":
                raise ValueError(error_msg)
            if not isinstance(value, expected_type):
                raise ValueError(f"{field_name} must be of type {expected_type.__name__}")
        api_endpoint = config["api_endpoint"]
        if not isinstance(api_endpoint, str):
            raise ValueError("API endpoint must be a string")
        if not api_endpoint.startswith("https://"):
            raise ValueError("API endpoint must use HTTPS")
        validation_rules = provider.validation_rules
        if isinstance(validation_rules, str):
            validation_rules = json.loads(validation_rules)
        api_endpoint = config.get("api_endpoint")
        if api_endpoint:
            pattern = validation_rules.get("endpoint")
            if pattern:
                import re

                if not re.match(pattern, api_endpoint):
                    raise ValueError(
                        "API endpoint does not match the required format specified by the provider."
                    )
        if provider.is_azure:
            deployment_name = config.get("deployment_name")
            if deployment_name:
                pattern = validation_rules.get("model_id")
                if pattern:
                    import re

                    if not re.match(pattern, deployment_name):
                        raise ValueError(
                            "Deployment name does not match the required format specified by the provider."
                        )
        else:
            config.pop("deployment_name", None)
        temperature = config.get("temperature")
        if temperature is not None and (temperature < 0 or temperature > 2):
            raise ValueError("Temperature must be between 0 and 2")
        max_tokens = config.get("max_tokens")
        if max_tokens is not None and max_tokens < 1:
            raise ValueError("Max tokens must be at least 1")
        if config.get("is_default", False):
            with db_session() as session:
                query = text(
                    """
                    SELECT COUNT(*) FROM models
                    WHERE is_default = TRUE
                    AND (:model_id IS NULL OR id != :model_id)
                    """
                )
                existing_defaults = session.execute(
                    query, {"model_id": model_id}
                ).scalar()
                if existing_defaults > 0 and model_id is None:
                    raise ValueError("Only one default model allowed")
