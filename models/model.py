"""
Module for handling model operations.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, TypeVar, List, cast

from sqlalchemy import text
from .base import db_session, get_db_pool
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Type variable for model dictionary
ModelDict = Dict[str, Any]
T = TypeVar('T')

@dataclass
class Model:
    """
    Dataclass representing a model.
    """
    id: int
    name: str
    deployment_name: str
    description: str
    model_type: str
    api_endpoint: str
    api_key: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None  # Should be None for o1-preview
    max_completion_tokens: Optional[int] = 8300  # o1-preview model can handle up to 8300 tokens
    is_default: bool = False
    requires_o1_handling: bool = False
    supports_streaming: bool = False  # Whether the model supports streaming responses
    api_version: str = "2024-10-01-preview"
    version: int = 1
    created_at: Optional[str] = None

    def __post_init__(self):
        """Validate or adjust fields after dataclass initialization."""
        self.id = int(self.id)

    @staticmethod
    def create_default_model() -> int:
        """Create a default model with comprehensive validation and fallback."""
        required_env_vars = {
            "DEFAULT_MODEL_NAME": "GPT-4",
            "DEFAULT_DEPLOYMENT_NAME": "gpt-4",
            "DEFAULT_MODEL_DESCRIPTION": "Default GPT-4 model",
            "DEFAULT_MODEL_TYPE": "azure",
            "DEFAULT_API_ENDPOINT": "https://your-resource.openai.azure.com",
            "AZURE_API_KEY": "your_default_api_key",
            "DEFAULT_TEMPERATURE": "1.0",
            "DEFAULT_MAX_TOKENS": "4000",
            "DEFAULT_MAX_COMPLETION_TOKENS": "500",
            "AZURE_API_VERSION": "2024-12-01-preview"
        }

        # Validate environment variables
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")

        default_model_data = {
            "name": os.getenv("DEFAULT_MODEL_NAME", required_env_vars["DEFAULT_MODEL_NAME"]),
            "deployment_name": os.getenv("DEFAULT_DEPLOYMENT_NAME", required_env_vars["DEFAULT_DEPLOYMENT_NAME"]),
            "description": os.getenv("DEFAULT_MODEL_DESCRIPTION", required_env_vars["DEFAULT_MODEL_DESCRIPTION"]),
            "model_type": os.getenv("DEFAULT_MODEL_TYPE", required_env_vars["DEFAULT_MODEL_TYPE"]),
            "api_endpoint": os.getenv("DEFAULT_API_ENDPOINT", required_env_vars["DEFAULT_API_ENDPOINT"]),
            "api_key": os.getenv("AZURE_API_KEY", required_env_vars["AZURE_API_KEY"]),
            "temperature": float(os.getenv("DEFAULT_TEMPERATURE", required_env_vars["DEFAULT_TEMPERATURE"])),
            "max_tokens": int(os.getenv("DEFAULT_MAX_TOKENS", required_env_vars["DEFAULT_MAX_TOKENS"])),
            "max_completion_tokens": int(os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", required_env_vars["DEFAULT_MAX_COMPLETION_TOKENS"])),
            "is_default": True,
            "requires_o1_handling": os.getenv("DEFAULT_REQUIRES_O1_HANDLING", "False").lower() == "true",
            "supports_streaming": os.getenv("DEFAULT_SUPPORTS_STREAMING", "True").lower() == "true",
            "api_version": os.getenv("AZURE_API_VERSION", required_env_vars["AZURE_API_VERSION"]),
            "version": 1,
        }

        try:
            # Validate model configuration before creation
            Model.validate_model_config(default_model_data)
            
            # Attempt to create the model
            model_id = Model.create(default_model_data)
            if model_id is None:
                raise ValueError("Failed to create default model")
            return model_id
        except Exception as e:
            logger.error(f"Failed to create default model: {e}")
            # Create a minimal valid model as fallback
            fallback_data = {
                "name": "Fallback Model",
                "deployment_name": "fallback-model",
                "description": "Minimal fallback model",
                "model_type": "azure",
                "api_endpoint": "https://fallback.openai.azure.com",
                "api_key": "fallback-key",
                "max_completion_tokens": 500,
                "is_default": True,
                "version": 1
            }
            logger.warning("Creating fallback model due to default model creation failure")
            return Model.create(fallback_data)

    @staticmethod
    def get_default() -> Optional["Model"]:
        """
        Retrieve the default model (where `is_default=1`).
        """
        pool = get_db_pool()
        with db_session(pool) as db:
            try:
                query = text("SELECT * FROM models WHERE is_default = :is_default")
                row = db.execute(query, {"is_default": True}).mappings().first()
                if row:
                    model_dict = dict(row)
                    # Exclude sensitive fields from logs
                    safe_model_dict = {k: v for k, v in model_dict.items() if k != 'api_key'}
                    logger.debug("Default model retrieved: %s", safe_model_dict)
                    return Model(**model_dict)
                logger.info("No default model found.")
                return None
            except Exception as e:
                logger.error("Error retrieving default model: %s", str(e))
                raise

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.
        """
        try:
            with db_session() as db:
                query = text("SELECT * FROM models WHERE id = :id")
                row = db.execute(query, {"id": model_id}).mappings().first()
                if row:
                    model_dict = dict(row)
                    
                    # Decrypt API key
                    from cryptography.fernet import Fernet
                    key = os.getenv('ENCRYPTION_KEY')
                    if not key:
                        raise ValueError("Encryption key not configured")
                    cipher_suite = Fernet(key)
                    model_dict["api_key"] = cipher_suite.decrypt(model_dict["api_key"].encode()).decode()
                    
                    # Exclude sensitive fields from logs
                    safe_model_dict = {k: v for k, v in model_dict.items() if k != 'api_key'}
                    logger.debug("Model retrieved by ID %d: %s", model_id, safe_model_dict)
                    return Model(**model_dict)
                logger.info("No model found with ID %d.", model_id)
                return None
        except Exception as e:
            logger.error("Error retrieving model by ID %d: %s", model_id, str(e))
            raise

    @staticmethod
    def get_all(limit: int = 10, offset: int = 0) -> List["Model"]:
        """
        Retrieve all models from the database, optionally paginated.
        """
        with db_session() as db:
            try:
                query = text(
                    """
                    SELECT * FROM models
                    ORDER BY created_at DESC LIMIT :limit
                    OFFSET :offset
                """
                )
                rows = (
                    db.execute(query, {"limit": limit, "offset": offset})
                    .mappings()
                    .all()
                )
                models: List[Model] = []
                for row in rows:
                    model_dict = dict(row)
                    models.append(Model(**model_dict))
                logger.debug(
                    f"Retrieved {len(models)} models with limit={limit} and offset={offset}"
                )
                return models
            except Exception as e:
                logger.error(f"Error retrieving all models: {e}")
                raise

    @staticmethod
    def set_default(model_id: int) -> None:
        """
        Set a model as the default, and remove the default status from any other model.
        """
        with db_session() as db:
            try:
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

                duplicate_check = (
                    db.execute(
                        text(
                            """
                    SELECT COUNT(*) as count FROM models WHERE is_default = :is_default
                """
                        ),
                        {"is_default": True},
                    )
                    .mappings()
                    .first()
                )
                if duplicate_check and duplicate_check["count"] > 1:
                    raise ValueError("More than one default model exists.")

                db.commit()
                logger.info(f"Model set as default (ID {model_id})")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to set default model {model_id}: {e}")
                raise

    @staticmethod
    def create(data: ModelDict) -> Optional[int]:
        """
        Create a new model record in the database.
        """
        try:
            with db_session() as db:
                logger.debug(f"Creating model with data: {data}")

                # Check for existing models with same name or deployment_name (case-insensitive)
                check_query = text("""
                    SELECT name, deployment_name
                    FROM models
                    WHERE LOWER(name) = LOWER(:name)
                    OR LOWER(deployment_name) = LOWER(:deployment_name)
                """)
                existing = db.execute(check_query, {
                    "name": data["name"],
                    "deployment_name": data["deployment_name"]
                }).fetchone()

                if existing:
                    if existing[0].lower() == data["name"].lower():
                        raise ValueError(f"A model with name '{data['name']}' already exists")
                    else:
                        raise ValueError(f"A model with deployment name '{data['deployment_name']}' already exists")

                # Validate model configuration
                Model.validate_model_config(data)

                # If setting as default, unset previous default
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
                """)
                result = db.execute(query, data)
                model_id = result.scalar()

                if model_id is None:
                    logger.error("Failed to create model - no ID returned")
                    return None

                # Create initial version
                Model.create_version(model_id, data)

                db.commit()
                logger.info(f"Model created with ID: {model_id}")
                return model_id
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create model: {e}")
            raise

    @staticmethod
    def update(model_id: int, data: ModelDict) -> None:
        """
        Update an existing model's attributes.
        """
        with db_session() as db:
            try:
                Model.validate_model_config(data)

                model = Model.get_by_id(model_id)
                if not model:
                    raise ValueError(f"Model with ID {model_id} not found.")

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
                    logger.info(f"No valid fields to update for model ID {model_id}")
                    return

                # If o1-preview handling is enabled, disable streaming
                if update_data.get("requires_o1_handling", False):
                    update_data["supports_streaming"] = False

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

                if update_data.get("is_default", False):
                    unset_default_query = text(
                        """
                        UPDATE models
                        SET is_default = 0
                        WHERE id != :model_id AND is_default = :is_default
                    """
                    )
                    db.execute(
                        unset_default_query, {"model_id": model_id, "is_default": True}
                    )

                # Create new version after update
                Model.create_version(model_id, data)

                db.commit()
                logger.info(f"Model updated (ID {model_id})")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update model {model_id}: {e}")
                raise

    @staticmethod
    def validate_model_config(config: ModelDict) -> None:
        """
        Validate model configuration parameters with enhanced security checks.
        """
        required_fields = [
            "name",
            "deployment_name",
            "api_endpoint",
            "api_key",
            "api_version",
            "model_type",
            "max_completion_tokens",
            "version"
        ]

        # Validate required fields
        for field_name in required_fields:
            val = config.get(field_name)
            if not val:
                raise ValueError(f"Missing required field: {field_name}")

        # Validate API endpoint format
        api_endpoint = config["api_endpoint"]
        if (
            not api_endpoint.startswith("https://")
            or "openai.azure.com" not in api_endpoint
        ):
            raise ValueError("Invalid Azure OpenAI API endpoint.")

        # Validate API key format (basic format check)
        api_key = config["api_key"]
        if not isinstance(api_key, str) or len(api_key) != 32:
            raise ValueError("API key must be a 32-character string")

        # Encrypt sensitive fields before storage
        from cryptography.fernet import Fernet
        key = os.getenv('ENCRYPTION_KEY')
        if not key:
            raise ValueError("Encryption key not configured")
            
        cipher_suite = Fernet(key)
        config["api_key"] = cipher_suite.encrypt(api_key.encode()).decode()

        # Validate temperature based on requires_o1_handling
        if config.get("requires_o1_handling", False):
            # For o1 models, temperature must be exactly 1.0
            temperature = config.get("temperature")
            if temperature is not None and float(temperature) != 1.0:
                raise ValueError("For o1 models, temperature must be exactly 1.0.")
            config["temperature"] = 1.0  # Ensure it is set to 1.0
            config["supports_streaming"] = False  # Disable streaming for o1-preview models
        else:
            temperature = config.get("temperature")
            if temperature is not None:
                try:
                    temperature = float(temperature)
                    if not (0 <= temperature <= 2):
                        raise ValueError("Temperature must be between 0 and 2.")
                    config["temperature"] = temperature  # Ensure correct type
                except ValueError:
                    raise ValueError("Temperature must be a valid number between 0 and 2.")
            else:
                config["temperature"] = None  # Explicitly set to None if not provided

        max_tokens = config.get("max_tokens", None)
        if max_tokens is not None and int(max_tokens) <= 0:
            raise ValueError("Max tokens must be a positive integer.")

        max_completion_tokens = config.get("max_completion_tokens")
        if max_completion_tokens is not None:
            try:
                max_completion_tokens = int(max_completion_tokens)
                max_limit = 8300 if config.get("requires_o1_handling") else 16384
                if not (1 <= max_completion_tokens <= max_limit):
                    raise ValueError(
                        f"max_completion_tokens must be between 1 and {max_limit}"
                    )
                config["max_completion_tokens"] = max_completion_tokens
            except (TypeError, ValueError):
                raise ValueError("max_completion_tokens must be a valid integer")

        # Additional validation for o1-preview models
        if config.get("requires_o1_handling", False):
            if config.get("temperature") not in (None, 1.0):
                raise ValueError("For o1 models, temperature must be exactly 1.0.")
            if config.get("supports_streaming", False):
                raise ValueError("o1 models do not support streaming.")

    @staticmethod
    def delete(model_id: int) -> None:
        """
        Delete a model from the database.
        """
        with db_session() as db:
            try:
                # Check if model is in use by any chats
                check_query = text(
                    """
                    SELECT COUNT(*) as count
                    FROM chats
                    WHERE model_id = :model_id
                """
                )
                result = db.execute(check_query, {"model_id": model_id}).mappings().first()
                if result and result["count"] > 0:
                    raise ValueError("Cannot delete model that is in use by chats")

                # Delete the model
                query = text("DELETE FROM models WHERE id = :model_id")
                db.execute(query, {"model_id": model_id})
                db.commit()
                sanitized_model_id = str(model_id).replace('\n', '').replace('\r', '')
                logger.info(f"Model deleted (ID {sanitized_model_id})")
            except Exception as e:
                db.rollback()
                sanitized_model_id = str(model_id).replace('\n', '').replace('\r', '')
                sanitized_error = str(e).replace('\n', ' ').replace('\r', ' ')
                logger.error(f"Failed to delete model {sanitized_model_id}: {sanitized_error}")
                raise

    @staticmethod
    def cleanup_orphaned_files() -> None:
        """Remove files without database references"""
        # TODO: Implement file cleanup logic using `text()`
        pass

    @staticmethod
    def get_user_chats(
        user_id: int, limit: int = 10, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch user chats with model information to avoid N+1 query problem.
        """
        with db_session() as db:
            try:
                query = text(
                    """
                    SELECT c.*, m.name as model_name
                    FROM chats c
                    LEFT JOIN models m ON c.model_id = m.id
                    WHERE c.user_id = :user_id
                    ORDER BY c.created_at DESC
                    LIMIT :limit OFFSET :offset
                """
                )
                result = db.execute(
                    query, {"user_id": user_id, "limit": limit, "offset": offset}
                ).fetchall()
                logger.debug(f"Retrieved {len(result)} chats for user ID {user_id}")
                return [dict(row) for row in result]
            except Exception as e:
                logger.error(f"Error retrieving chats for user {user_id}: {e}")
                raise

    @staticmethod
    def get_immutable_fields(model_id: int) -> List[str]:
        """Get fields that cannot be modified."""
        return ['id', 'created_at']

    @staticmethod
    def get_version_history(model_id: int, limit: int = 10, offset: int = 0) -> List[ModelDict]:
        """Get version history for model."""
        with db_session() as db:
            query = text("""
                SELECT * FROM model_versions
                WHERE model_id = :model_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            result = db.execute(query, {
                "model_id": model_id,
                "limit": limit,
                "offset": offset
            })
            return [dict(row) for row in result]

    @staticmethod
    def revert_to_version(model_id: int, version: int) -> None:
        """Revert model to previous version."""
        import json
        with db_session() as db:
            try:
                # Get version data
                version_query = text("""
                    SELECT data FROM model_versions
                    WHERE model_id = :model_id AND version = :version
                """)
                version_data = db.execute(version_query, {
                    "model_id": model_id,
                    "version": version
                }).scalar()

                if not version_data:
                    raise ValueError(f"Version {version} not found")

                # Parse JSON string back to dictionary
                version_dict = json.loads(version_data)

                # Update model with version data
                Model.update(model_id, version_dict)
                db.commit()
            except json.JSONDecodeError as e:
                db.rollback()
                logger.error(f"Invalid version data format: {e}")
                raise ValueError(f"Invalid version data format: {e}")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to revert model {model_id} to version {version}: {e}")
                raise

    @staticmethod
    def create_version(model_id: int, data: ModelDict) -> None:
        """Create new version record."""
        import json
        with db_session() as db:
            try:
                # Get current version
                curr_version = db.execute(text(
                    "SELECT MAX(version) FROM model_versions WHERE model_id = :id"
                ), {"id": model_id}).scalar() or 0

                # Convert dictionary to JSON string
                json_data = json.dumps(data)

                # Insert new version
                db.execute(text("""
                    INSERT INTO model_versions (model_id, version, data)
                    VALUES (:model_id, :version, :data)
                """), {
                    "model_id": model_id,
                    "version": curr_version + 1,
                    "data": json_data
                })
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create version for model {model_id}: {e}")
                raise
