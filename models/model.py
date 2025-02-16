# models/model.py
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any, List, ClassVar, TYPE_CHECKING

from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session

from config import Config
from logging_config import get_logger

# Forward references for type hints
if TYPE_CHECKING:
    from .chat import Chat
    from .provider import Provider

logger = get_logger(__name__)

ModelDict = Dict[str, Any]


class ModelBaseException(Exception):
    """Custom exception class for model-related errors."""
    pass


class ModelValidationError(ModelBaseException):
    """Raised when model validation fails."""
    pass


class ModelCreationError(ModelBaseException):
    """Raised when model creation fails."""
    pass


class ModelUpdateError(ModelBaseException):
    """Raised when model update fails."""
    pass


class BaseMismatchError(ModelBaseException):
    """Raised when code references the wrong base class or mismatch occurs."""
    pass


from .base import Base


class Model(Base):
    """
    Represents an AI model configuration using SQLAlchemy ORM.
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    deployment_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    api_endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key: Mapped[str] = mapped_column(String(200), nullable=False)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="models",
        lazy="joined"
    )
    chats: Mapped[List["Chat"]] = relationship(
        "Chat",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="select"
    )

    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    max_completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=8300)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_o1_handling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_version: Mapped[str] = mapped_column(String(50), nullable=False, default="2024-12-01-preview")
    reasoning_effort: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")

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
            "streaming": False,
            "max_tokens": 200000,
            "max_completion_tokens": 100000,
            "supports_json_mode": True,
            "requires_reasoning_effort": True,
            "supports_vision": True,
            "api_version": "2025-01-01-preview",
            "default_reasoning_effort": "medium",
            "required_headers": {
                "api-key": "{api_key}",
                "Content-Type": "application/json"
            }
        },
        "o1-mini": {
            "fixed_temperature": True,
            "streaming": False,
            "max_tokens": 100000,
            "max_completion_tokens": 50000,
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

    def __init__(self, **kwargs) -> None:
        """
        Initialize the Model instance. 
        IMPORTANT: we do NOT call apply_provider_constraints here anymore
        because it requires a session. 
        That step should happen after instantiation, 
        in the create or update flow where a Session is available.
        """
        for key, value in kwargs.items():
            if key in ("id", "provider_id") and value is not None:
                value = int(value)
            setattr(self, key, value)

    def apply_provider_constraints(self, session: Session) -> None:
        """
        Apply provider-specific constraints to model configuration, using the given session.
        """
        from .provider import Provider

        provider = Provider.get_by_id(session, self.provider_id) if hasattr(self, 'provider_id') else None
        if not provider or not provider.capabilities:
            return

        provider_caps = provider.capabilities
        # If provider fixes temperature
        if provider_caps.get("fixed_temperature"):
            self.temperature = provider_caps["fixed_temperature"]
        # If there's a maximum token limit
        if "max_tokens" in provider_caps and self.max_completion_tokens:
            self.max_completion_tokens = min(
                self.max_completion_tokens,
                int(provider_caps["max_tokens"])  # Convert to int to ensure type compatibility
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert model to dictionary, excluding sensitive data.
        """
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "name": self.name,
            "deployment_name": self.deployment_name,
            "description": self.description,
            "model_type": self.model_type,
            "max_tokens": self.max_tokens,
            "max_completion_tokens": self.max_completion_tokens,
            "requires_o1_handling": self.requires_o1_handling,
            "supports_streaming": self.supports_streaming,
            "api_version": self.api_version,
            "reasoning_effort": self.reasoning_effort,
        }

    @staticmethod
    def get_all(session: Session) -> List["Model"]:
        """
        Retrieve all models from the database using raw SQL. 
        Decrypt api_key if possible.
        """
        try:
            config = Config()
            query = text("SELECT * FROM models ORDER BY name")
            results = session.execute(query).mappings().all()

            from utils.encryption import decrypt_api_key, EncryptionError

            models = []
            for row in results:
                model_dict = dict(row)
                model_dict.pop("store_completion", None)

                # Convert to proper types
                if model_dict.get("id") is not None:
                    model_dict["id"] = int(model_dict["id"])
                if model_dict.get("provider_id") is not None:
                    model_dict["provider_id"] = int(model_dict["provider_id"])
                if model_dict.get("temperature") is not None:
                    model_dict["temperature"] = float(model_dict["temperature"])
                if model_dict.get("max_tokens") is not None:
                    model_dict["max_tokens"] = int(model_dict["max_tokens"])
                if model_dict.get("max_completion_tokens") is not None:
                    model_dict["max_completion_tokens"] = int(model_dict["max_completion_tokens"])

                for bool_field in ["requires_o1_handling", "supports_streaming", "is_default"]:
                    value = model_dict.get(bool_field)
                    if isinstance(value, str):
                        model_dict[bool_field] = value.lower() in ("true", "t", "1")
                    elif isinstance(value, int):
                        model_dict[bool_field] = bool(value)

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
    def get_immutable_fields(session: Session, model_id: int) -> List[str]:
        """
        Retrieve a list of fields that cannot be modified for an existing model.
        """
        try:
            query = text("SELECT model_type FROM models WHERE id = :id")
            model_type = session.execute(query, {"id": model_id}).scalar()
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
    def get_by_id(session: Session, model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID, decrypting the API key if possible.
        """
        try:
            config = Config()
            query = text("SELECT * FROM models WHERE id = :id")
            row = session.execute(query, {"id": model_id}).mappings().first()
            if not row:
                logger.warning("No model found with ID %d", model_id)
                return None

            model_dict = dict(row)
            model_dict.pop("store_completion", None)

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

            for bool_field in ["requires_o1_handling", "supports_streaming", "is_default"]:
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
    def create(session: Session, data: ModelDict) -> Optional[int]:
        """
        Create a new model record, validating the data first, then inserting.
        """
        try:
            logger.debug(
                "Creating model with data: %s",
                {k: v if k != "api_key" else "****" for k, v in data.items()},
            )

            from .provider import Provider
            from utils.encryption import encrypt_api_key
            config = Config()

            # Encrypt the API key if present
            if "api_key" in data:
                try:
                    data["api_key"] = encrypt_api_key(data["api_key"], config.ENCRYPTION_KEY)
                except Exception as e:
                    logger.error("Failed to encrypt API key: %s", str(e))
                    raise ModelCreationError(f"Failed to encrypt API key: {str(e)}")

            # Validate the provider
            provider = Provider.get_by_id(session, data["provider_id"])
            if not provider:
                raise ModelCreationError("Invalid provider_id")

            # Validate the model config (pass session)
            Model.validate_model_config(data, session)

            # If is_default is requested, ensure no conflicts
            if data.get("is_default", False):
                session.execute(
                    text("UPDATE models SET is_default = FALSE WHERE is_default = TRUE")
                )

            # Insert
            query = text(
                """
                INSERT INTO models (
                    provider_id, name, deployment_name, description, api_endpoint, api_key,
                    api_version, temperature, max_tokens, max_completion_tokens,
                    model_type, requires_o1_handling, supports_streaming, is_default,
                    reasoning_effort, created_at
                ) VALUES (
                    :provider_id, :name, :deployment_name, :description, :api_endpoint, :api_key,
                    :api_version, :temperature, :max_tokens, :max_completion_tokens,
                    :model_type, :requires_o1_handling, :supports_streaming, :is_default,
                    :reasoning_effort, NOW()
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
            logger.error("Failed to create model: %s", e, exc_info=True)
            session.rollback()
            raise ModelCreationError(str(e)) from e

    @staticmethod
    def update(session: Session, model_id: int, data: Dict[str, Any]) -> None:
        """
        Update model with validated data, ensuring concurrency control via version.
        """
        try:
            if not model_id:
                raise ModelUpdateError("Model ID is required")

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

            if "api_key" in update_data:
                from utils.encryption import encrypt_api_key
                config = Config()
                try:
                    update_data["api_key"] = encrypt_api_key(update_data["api_key"], config.ENCRYPTION_KEY)
                except Exception as e:
                    logger.error("Failed to encrypt API key: %s", str(e))
                    raise ModelUpdateError(f"Failed to encrypt API key: {str(e)}")

            current_model = Model.get_by_id(session, model_id)
            if not current_model:
                raise ModelUpdateError(f"Model with ID {model_id} not found")

            # Validate model config with session
            Model.validate_model_config(update_data, session, model_id)

            # Check concurrency (optimistic locking) - get current version
            current_version = session.execute(
                text("SELECT version FROM models WHERE id = :model_id"),
                {"model_id": model_id},
            ).scalar()
            if current_version is None:
                raise ModelUpdateError(f"Model with ID {model_id} not found (version issue)")

            update_data["version"] = current_version + 1

            set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
            params = {**update_data, "model_id": model_id, "current_version": current_version}
            query = text(
                f"""
                UPDATE models
                SET {set_clause}
                WHERE id = :model_id AND version = :current_version
                RETURNING version
                """
            ).bindparams(**params)
            result = session.execute(query)
            if result.rowcount == 0:
                raise ModelUpdateError(
                    "Model was modified by another user. Please refresh and try again."
                )

            # If we set is_default = True, unset is_default on others
            if update_data.get("is_default", False):
                session.execute(
                    text(
                        """
                        UPDATE models
                        SET is_default = FALSE
                        WHERE id != :model_id AND is_default = TRUE
                        """
                    ),
                    {
                        "model_id": model_id,
                    },
                )

            session.commit()
            logger.info("Model updated (ID %d)", model_id)

        except Exception as e:
            logger.error("Failed to update model %d: %s", model_id, e, exc_info=True)
            session.rollback()
            raise ModelUpdateError(str(e)) from e

    @staticmethod
    def delete(session: Session, model_id: int) -> None:
        """
        Delete a model from the database, ensuring it's not default or in use.
        """
        try:
            # Check if default
            is_default_query = text(
                "SELECT is_default FROM models WHERE id = :model_id"
            )
            is_default_result = session.execute(
                is_default_query, {"model_id": model_id}
            ).scalar()
            if is_default_result:
                default_count_query = text(
                    "SELECT COUNT(*) FROM models WHERE is_default = TRUE"
                )
                default_count = session.execute(default_count_query).scalar()
                if default_count == 1:
                    raise ModelUpdateError("Cannot delete the last default model")

            # Check if in use by any chats
            check_query = text(
                """
                SELECT COUNT(*) as count
                FROM chats
                WHERE model_id = :model_id
                """
            )
            result = session.execute(check_query, {"model_id": model_id}).mappings().first()
            if result and result["count"] > 0:
                raise ModelUpdateError("Cannot delete model that is in use by chats")

            # Delete references in model_versions
            delete_versions_query = text(
                "DELETE FROM model_versions WHERE model_id = :model_id"
            )
            session.execute(delete_versions_query, {"model_id": model_id})

            query = text("DELETE FROM models WHERE id = :model_id")
            session.execute(query, {"model_id": model_id})
            session.commit()
            logger.info("Model deleted (ID %d)", model_id)
        except Exception as e:
            session.rollback()
            logger.error("Failed to delete model %d: %s", model_id, e)
            raise ModelUpdateError(str(e)) from e

    @staticmethod
    def get_default(session: Session) -> Optional["Model"]:
        """
        Retrieve the default model.
        """
        try:
            query = text("SELECT * FROM models WHERE is_default = TRUE")
            result = session.execute(query).mappings().first()
            if not result:
                return None

            model_dict = dict(result)
            if model_dict.get("id") is not None:
                model_dict["id"] = int(model_dict["id"])
            if model_dict.get("provider_id") is not None:
                model_dict["provider_id"] = int(model_dict["provider_id"])
            if model_dict.get("temperature") is not None:
                model_dict["temperature"] = float(model_dict["temperature"])
            if model_dict.get("max_tokens") is not None:
                model_dict["max_tokens"] = int(model_dict["max_tokens"])
            if model_dict.get("max_completion_tokens") is not None:
                model_dict["max_completion_tokens"] = int(model_dict["max_completion_tokens"])

            return Model(**model_dict)
        except Exception as e:
            logger.error("Failed to retrieve default model: %s", e)
            return None

    @staticmethod
    def validate_model_config(
        config: ModelDict,
        session: Session,
        model_id: Optional[int] = None
    ) -> None:
        """
        Validate model configuration parameters, requiring a session.
        """
        from .provider import Provider
        provider = Provider.get_by_id(session, config["provider_id"])
        if not provider:
            raise ModelValidationError("Invalid provider_id")

        # If model_type == "o1", check Azure style constraints
        if config.get("model_type") == "o1":
            api_key = config.get("api_key", "")
            if not (api_key.startswith("sk-") or api_key.startswith("vOJI")):
                raise ModelValidationError("Azure API keys must start with 'sk-' or 'vOJI'")
            endpoint = config.get("api_endpoint", "")
            if not endpoint.startswith("https://o1models."):
                raise ModelValidationError("o1 models require a specific Azure endpoint format")
            config["requires_o1_handling"] = True

        provider_caps = provider.capabilities
        if provider_caps.get("fixed_temperature"):
            config["temperature"] = 1.0
        config["supports_streaming"] = provider_caps.get("streaming", True)

        model_type = config.get("model_type", "").lower()
        requires_o1 = config.get("requires_o1_handling", False)
        is_o1_preview = (model_type == "o1-preview") and requires_o1
        model_caps = Model.PROVIDER_CAPABILITIES.get(model_type, {})

        # If o1-preview, check recommended max
        if is_o1_preview:
            max_tokens = config.get("max_completion_tokens", 8300)
            if not (1 <= max_tokens <= 100000):
                raise ModelValidationError(
                    "For o1-preview models, max_completion_tokens must be between 1 and 100000"
                )
            config["max_completion_tokens"] = max_tokens
        else:
            max_tokens = config.get("max_completion_tokens")
            if max_tokens is not None and max_tokens <= 0:
                raise ModelValidationError("max_completion_tokens must be positive")
            if "max_tokens" in model_caps:
                config["max_completion_tokens"] = min(
                    max_tokens or model_caps["max_tokens"],
                    model_caps["max_tokens"]
                )

        # o-series validations
        is_o_series = model_type.startswith("o")
        if is_o_series:
            # Validate reasoning_effort
            reasoning_effort = config.get("reasoning_effort", "medium")
            if reasoning_effort not in ["low", "medium", "high"]:
                raise ModelValidationError("reasoning_effort must be one of: low, medium, high")
            config["reasoning_effort"] = reasoning_effort

            # Validate max_completion_tokens
            max_completion_tokens = config.get("max_completion_tokens")
            if max_completion_tokens is not None:
                max_allowed = model_caps.get("max_completion_tokens", 100000)
                if not (1 <= max_completion_tokens <= max_allowed):
                    raise ModelValidationError(
                        f"max_completion_tokens must be between 1 and {max_allowed} for {model_type}"
                    )
            config["temperature"] = 1.0
            config["max_tokens"] = model_caps.get("max_tokens", 200000)
            config.pop("top_p", None)
            config.pop("frequency_penalty", None)
            config.pop("presence_penalty", None)
        else:
            config["reasoning_effort"] = "medium"
            config["max_tokens"] = config.get("max_tokens", 16384)

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
                raise ModelValidationError(f"Missing required field: {field_name}")
            value = config[field_name]
            if not value:
                raise ModelValidationError(error_msg)
            if not isinstance(value, expected_type):
                raise ModelValidationError(f"{field_name} must be of type {expected_type.__name__}")

        api_endpoint = config["api_endpoint"]
        if not isinstance(api_endpoint, str):
            raise ModelValidationError("API endpoint must be a string")
        if not api_endpoint.startswith("https://"):
            raise ModelValidationError("API endpoint must use HTTPS")

        validation_rules = provider.validation_rules
        if isinstance(validation_rules, str):
            validation_rules = json.loads(validation_rules)

        if api_endpoint:
            pattern = validation_rules.get("endpoint")
            if pattern:
                if not re.match(pattern, api_endpoint):
                    raise ModelValidationError(
                        "API endpoint does not match the required format specified by the provider."
                    )

        if provider.is_azure:
            deployment_name = config.get("deployment_name")
            if deployment_name:
                pattern = validation_rules.get("model_id")
                if pattern:
                    if not re.match(pattern, deployment_name):
                        raise ModelValidationError(
                            "Deployment name does not match the required format specified by the provider."
                        )
        else:
            config.pop("deployment_name", None)

        temperature = config.get("temperature")
        if temperature is not None and (temperature < 0 or temperature > 2):
            raise ModelValidationError("Temperature must be between 0 and 2")

        max_tokens = config.get("max_tokens")
        if max_tokens is not None and max_tokens < 1:
            raise ModelValidationError("Max tokens must be at least 1")

        # If this is intended as the default model, ensure no duplicates
        if config.get("is_default", False):
            query = text(
                """
                SELECT COUNT(*) FROM models
                WHERE is_default = TRUE
                AND (:model_id IS NULL OR id != :model_id)
                """
            )
            existing_defaults = session.execute(query, {"model_id": model_id}).scalar()
            # If there's an existing default and we are creating a brand new model, fail
            if existing_defaults > 0 and model_id is None:
                raise ModelValidationError("Only one default model allowed")
