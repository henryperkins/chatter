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

    def __post_init__(self):
        """Validate and adjust fields after initialization."""
        self.id = int(self.id)

    # region CRUD Operations

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
            with db_session() as db:
                logger.debug(
                    "Creating model with data: %s",
                    {k: v if k != "api_key" else "****" for k, v in data.items()},
                )

                # Check for existing models with same name/deployment
                check_query = text(
                    """
                    SELECT name, deployment_name
                    FROM models
                    WHERE (LOWER(name) = LOWER(:name)
                    OR LOWER(deployment_name) = LOWER(:deployment_name))
                    AND (NOT is_default OR :is_default = 1)
                """
                )
                existing = db.execute(
                    check_query,
                    {
                        "name": data["name"],
                        "deployment_name": data["deployment_name"],
                        "is_default": data.get("is_default", False)
                    },
                ).fetchone()

                if existing:
                    field = (
                        "name"
                        if existing[0].lower() == data["name"].lower()
                        else "deployment_name"
                    )
                    raise ValueError(f"A model with this {field} already exists")

                # Validate configuration
                Model.validate_model_config(data)

                # Update default status if needed
                if data.get("is_default", False):
                    db.execute(
                        text("UPDATE models SET is_default = 0 WHERE is_default = 1")
                    )

                # Insert new model
                query = text(
                    """
                    INSERT INTO models (
                        name, deployment_name, description, api_endpoint, api_key,
                        api_version, temperature, max_tokens, max_completion_tokens,
                        model_type, requires_o1_handling, supports_streaming, is_default, version,
                        created_at
                    ) VALUES (
                        :name, :deployment_name, :description, :api_endpoint, :api_key,
                        :api_version, :temperature, :max_tokens, :max_completion_tokens,
                        :model_type, :requires_o1_handling, :supports_streaming, :is_default, :version,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING id
                """
                )
                result = db.execute(query, data)
                model_id = result.scalar()

                if model_id is None:
                    logger.error("Failed to create model - no ID returned")
                    return None

                # Create initial version
                Model.create_version(model_id, data)

                db.commit()
                logger.info("Model created with ID: %d", model_id)
                return model_id

        except Exception as e:
            db.rollback()
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
            with db_session() as db:
                query = text("SELECT * FROM models WHERE id = :id")
                row = db.execute(query, {"id": model_id}).mappings().first()

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
                
                # Create and return the model instance
                model = Model(**model_dict)
                
                # Validate the model configuration
                required_attrs = [
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
                }
                update_data = {
                    key: value for key, value in data.items() if key in allowed_fields
                }

                if not update_data:
                    logger.info("No valid fields to update for model ID %d", model_id)
                    return

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
                            text("UPDATE models SET is_default = 0 WHERE id != :model_id"),
                            {"model_id": model_id}
                        )
                    else:
                        # Ensure at least one model remains default when unsetting is_default
                        if update_data.get("is_default") is False:
                            default_count = db.execute(
                                text("SELECT COUNT(*) FROM models WHERE is_default = 1 AND id != :model_id"),
                                {"model_id": model_id}
                            ).scalar()
                            if default_count == 0:
                                raise ValueError("Cannot unset default model without setting another as default")

                # Validate configuration before update
                Model.validate_model_config(update_data)

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
                            SET is_default = 0
                            WHERE id != :model_id AND is_default = :is_default
                        """
                        ),
                        {"model_id": model_id, "is_default": True},
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
            ValueError: If model is in use by chats
        """
        with db_session() as db:
            try:
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
        default_model_data = {
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
                query = text("SELECT * FROM models WHERE is_default = :is_default")
                row = db.execute(query, {"is_default": True}).mappings().first()
                if row:
                    model_dict = dict(row)
                    safe_dict = {k: v for k, v in model_dict.items() if k != "api_key"}
                    logger.debug("Default model retrieved: %s", safe_dict)
                    return Model(**model_dict)
                logger.info("No default model found")
                return None
            except Exception as e:
                logger.error("Error retrieving default model: %s", e)
                raise

    @staticmethod
    def get_all(limit: int = 10, offset: int = 0, exclude_id: Optional[int] = None) -> List["Model"]:
        """
        Retrieve all models with pagination.

        Args:
            limit: Maximum number of models to return
            offset: Number of models to skip
            exclude_id: ID of the model to exclude from results

        Returns:
            List[Model]: List of model instances
        """
        with db_session() as db:
            try:
                if exclude_id is not None:
                    query = text(
                        """
                        SELECT * FROM models
                        WHERE id != :exclude_id
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset
                    """
                    )
                    params = {"exclude_id": exclude_id, "limit": limit, "offset": offset}
                else:
                    query = text(
                        """
                        SELECT * FROM models
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset
                    """
                    )
                    params = {"limit": limit, "offset": offset}

                rows = (
                    db.execute(query, params)
                    .mappings()
                    .all()
                )

                models = [Model(**dict(row)) for row in rows]
                logger.debug(
                    "Retrieved %d models (limit=%d, offset=%d, exclude_id=%s)",
                    len(models),
                    limit,
                    offset,
                    exclude_id,
                )
                return models
            except Exception as e:
                logger.error("Error retrieving all models: %s", e)
                raise

    @staticmethod
    def set_default(model_id: int) -> None:
        """
        Set a model as the default.

        Args:
            model_id: ID of the model to set as default

        Raises:
            ValueError: If multiple default models exist
        """
        with db_session() as db:
            try:
                # Update default status
                db.execute(
                    text(
                        "UPDATE models SET is_default = 0 WHERE is_default = :current_default"
                    ),
                    {"current_default": True},
                )
                db.execute(
                    text("UPDATE models SET is_default = 1 WHERE id = :model_id"),
                    {"model_id": model_id},
                )

                # Verify single default
                duplicate_check = (
                    db.execute(
                        text(
                            "SELECT COUNT(*) as count FROM models WHERE is_default = :is_default"
                        ),
                        {"is_default": True},
                    )
                    .mappings()
                    .first()
                )

                if duplicate_check and duplicate_check["count"] > 1:
                    raise ValueError("More than one default model exists")

                db.commit()
                logger.info("Model set as default (ID %d)", model_id)

            except Exception as e:
                db.rollback()
                logger.error("Failed to set default model %d: %s", model_id, e)
                raise

    # endregion

    # region Validation and Configuration

    @staticmethod
    def validate_model_config(config: ModelDict) -> None:
        """
        Validate model configuration parameters.

        Args:
            config: Dictionary containing model configuration

        Raises:
            ValueError: If configuration is invalid
        """
        # Check encryption key
        if not Config.ENCRYPTION_KEY:
            raise ValueError("ENCRYPTION_KEY environment variable must be set")
        if len(Config.ENCRYPTION_KEY) != 44:
            raise ValueError("ENCRYPTION_KEY must be a 32-byte URL-safe base64-encoded string")

        # Validate required fields
        required_fields = [
            "name",
            "deployment_name",
            "api_endpoint",
            "api_key",
            "api_version",
            "model_type",
            "max_completion_tokens",
            "version",
        ]
        for field in required_fields:
            if not config.get(field):
                raise ValueError(f"Missing required field: {field}")

        # Validate API endpoint and version
        api_endpoint = config["api_endpoint"]
        if (
            not api_endpoint.startswith("https://")
            or "openai.azure.com" not in api_endpoint
        ):
            raise ValueError("Invalid Azure OpenAI API endpoint")
            
        # Validate API version
        valid_versions = ["2024-12-01-preview", "2023-07-01-preview", "2023-03-15-preview"]
        if config["api_version"] not in valid_versions:
            raise ValueError(f"Invalid API version. Must be one of: {', '.join(valid_versions)}")

        # Validate API key
        api_key = config["api_key"]
        if not isinstance(api_key, str) or len(api_key) < 32:
            raise ValueError("API key must be at least 32 characters long")
        if len(api_key) > 512:
            raise ValueError("API key must be less than 512 characters")

        # Encrypt API key with proper error handling
        key = Config.ENCRYPTION_KEY
        if not key:
            raise ValueError("Encryption key not configured")
            
        try:
            if isinstance(key, str):
                key = key.encode()
            cipher_suite = Fernet(key)
            config["api_key"] = cipher_suite.encrypt(api_key.encode()).decode()
        except Exception as e:
            logger.error("Failed to encrypt API key: %s", str(e))
            raise ValueError("Failed to encrypt API key. Please verify encryption configuration")

        # Validate temperature
        if config.get("requires_o1_handling", False):
            config["temperature"] = 1.0
            config["supports_streaming"] = False
        elif "temperature" in config:
            try:
                temp = float(config["temperature"])
                if not 0 <= temp <= 2:
                    raise ValueError("Temperature must be between 0 and 2")
                config["temperature"] = temp
            except (TypeError, ValueError):
                raise ValueError("Temperature must be a valid number between 0 and 2")

        # Validate token limits
        if "max_tokens" in config and config["max_tokens"] is not None:
            if int(config["max_tokens"]) <= 0:
                raise ValueError("Max tokens must be a positive integer")

        max_completion_tokens = config.get("max_completion_tokens")
        if max_completion_tokens is not None:
            try:
                tokens = int(max_completion_tokens)
                max_limit = 8300 if config.get("requires_o1_handling") else 16384
                if not 1 <= tokens <= max_limit:
                    raise ValueError(
                        f"max_completion_tokens must be between 1 and {max_limit}"
                    )
                config["max_completion_tokens"] = tokens
            except (TypeError, ValueError):
                raise ValueError("max_completion_tokens must be a valid integer")

    # endregion

    # region Version Control

    @staticmethod
    def create_version(model_id: int, data: ModelDict) -> None:
        """
        Create a new version record for a model.

        Args:
            model_id: ID of the model
            data: Current model configuration
        """
        with db_session() as db:
            try:
                curr_version = (
                    db.execute(
                        text(
                            "SELECT MAX(version) FROM model_versions WHERE model_id = :id"
                        ),
                        {"id": model_id},
                    ).scalar()
                    or 0
                )

                json_data = json.dumps(data)
                db.execute(
                    text(
                        """
                        INSERT INTO model_versions (model_id, version, data)
                        VALUES (:model_id, :version, :data)
                    """
                    ),
                    {
                        "model_id": model_id,
                        "version": curr_version + 1,
                        "data": json_data,
                    },
                )
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("Failed to create version for model %d: %s", model_id, e)
                raise

    @staticmethod
    def get_version_history(
        model_id: int, limit: int = 10, offset: int = 0
    ) -> List[ModelDict]:
        """
        Get version history for a model.

        Args:
            model_id: ID of the model
            limit: Maximum number of versions to return
            offset: Number of versions to skip

        Returns:
            List[ModelDict]: List of version records
        """
        with db_session() as db:
            query = text(
                """
                SELECT * FROM model_versions
                WHERE model_id = :model_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """
            )
            result = db.execute(
                query, {"model_id": model_id, "limit": limit, "offset": offset}
            )
            return [dict(row) for row in result]

    @staticmethod
    def revert_to_version(model_id: int, version: int) -> None:
        """
        Revert a model to a previous version.

        Args:
            model_id: ID of the model
            version: Version number to revert to

        Raises:
            ValueError: If version not found or invalid
        """
        with db_session() as db:
            try:
                version_query = text(
                    """
                    SELECT data FROM model_versions
                    WHERE model_id = :model_id AND version = :version
                """
                )
                version_data = db.execute(
                    version_query, {"model_id": model_id, "version": version}
                ).scalar()

                if not version_data:
                    raise ValueError(f"Version {version} not found")

                version_dict = json.loads(version_data)
                Model.update(model_id, version_dict)
                db.commit()
            except json.JSONDecodeError as e:
                db.rollback()
                logger.error("Invalid version data format: %s", e)
                raise ValueError(f"Invalid version data format: {e}")
            except Exception as e:
                db.rollback()
                logger.error(
                    "Failed to revert model %d to version %d: %s", model_id, version, e
                )
                raise

    # endregion

    @staticmethod
    def get_immutable_fields(model_id: int) -> List[str]:
        """Get fields that cannot be modified."""
        return ["id", "created_at"]
