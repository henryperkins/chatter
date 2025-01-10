import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from sqlalchemy import text

from .base import db_session

logger = logging.getLogger(__name__)


@dataclass
class Model:
    """
    Represents an AI model in the system.
    """

    id: int
    name: str
    deployment_name: str
    description: Optional[str]
    model_type: str
    api_endpoint: str
    api_key: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: int = 8300  # o1-preview model can handle up to 8300 tokens
    is_default: bool = False
    requires_o1_handling: bool = False
    api_version: str = "2024-10-01-preview"
    version: int = 1
    created_at: Optional[str] = None

    def __post_init__(self):
        """Validate or adjust fields after dataclass initialization."""
        self.id = int(self.id)

    @staticmethod
    def get_default() -> Optional["Model"]:
        """
        Retrieve the default model (where `is_default=1`).
        """
        with db_session() as db:
            try:
                query = text("SELECT * FROM models WHERE is_default = :is_default")
                row = db.execute(query, {"is_default": True}).mappings().first()
                if row:
                    model_dict = dict(row)
                    logger.debug(f"Default model retrieved: {model_dict}")
                    return Model(**model_dict)
                logger.info("No default model found.")
                return None
            except Exception as e:
                logger.error(f"Error retrieving default model: {e}")
                raise

    @staticmethod
    def get_by_id(model_id: int) -> Optional["Model"]:
        """
        Retrieve a model by its ID.
        """
        with db_session() as db:
            try:
                query = text("SELECT * FROM models WHERE id = :model_id")
                row = db.execute(query, {"model_id": model_id}).mappings().first()
                if row:
                    model_dict = dict(row)
                    logger.debug(f"Model retrieved by ID {model_id}: {model_dict}")
                    return Model(**model_dict)
                logger.info(f"No model found with ID: {model_id}")
                return None
            except Exception as e:
                logger.error(f"Error retrieving model by ID {model_id}: {e}")
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
                    ORDER BY created_at DESC 
                    LIMIT :limit OFFSET :offset
                """
                )
                rows = (
                    db.execute(query, {"limit": limit, "offset": offset})
                    .mappings()
                    .all()
                )
                models = []
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
    def create(data: Dict[str, Any]) -> Optional[int]:
        """
        Create a new model record in the database.
        """
        with db_session() as db:
            try:
                if data.get("requires_o1_handling", False):
                    data["temperature"] = None

                query = text(
                    """
                    INSERT INTO models (
                        name, deployment_name, description, api_endpoint, api_key,
                        api_version, temperature, max_tokens, max_completion_tokens,
                        model_type, requires_o1_handling, is_default, version
                    ) VALUES (
                        :name, :deployment_name, :description, :api_endpoint, :api_key,
                        :api_version, :temperature, :max_tokens, :max_completion_tokens,
                        :model_type, :requires_o1_handling, :is_default, :version
                    )
                    RETURNING id
                """
                )
                result = db.execute(query, data)
                model_id = result.scalar()

                if model_id is None:
                    logger.error("Failed to create model - no ID returned")
                    return None

                if data.get("is_default", False):
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
                    db.commit()

                logger.info(f"Model created with ID: {model_id}")
                return model_id
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create model: {e}")
                raise

    @staticmethod
    def update(model_id: int, data: Dict[str, Any]) -> None:
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
                    "is_default",
                    "version",
                }
                update_data = {
                    key: value for key, value in data.items() if key in allowed_fields
                }

                if not update_data:
                    logger.info(f"No valid fields to update for model ID {model_id}")
                    return

                set_clause = ", ".join(f"{key} = :{key}" for key in update_data)
                params = {**update_data, "model_id": model_id}

                query = text(
                    f"""
                    UPDATE models
                    SET {set_clause}
                    WHERE id = :model_id
                """
                )

                db.execute(query, params)

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

                db.commit()
                logger.info(f"Model updated (ID {model_id})")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update model {model_id}: {e}")
                raise

    @staticmethod
    def validate_model_config(config: Dict[str, Any]) -> None:
        """
        Validate model configuration parameters.
        """
        required_fields = [
            "name",
            "deployment_name",
            "api_endpoint",
            "api_key",
            "api_version",
            "model_type",
            "max_completion_tokens",
            "version"  # Add version to required fields
        ]

        for field_name in required_fields:
            val = config.get(field_name)
            if not val:
                raise ValueError(f"Missing required field: {field_name}")

        api_endpoint = config["api_endpoint"]
        if (
            not api_endpoint.startswith("https://")
            or "openai.azure.com" not in api_endpoint
        ):
            raise ValueError("Invalid Azure OpenAI API endpoint.")

        # Validate version field
        version = config.get("version")
        if version is not None and not isinstance(version, int):
            raise ValueError("Version must be an integer")

        if not config.get("requires_o1_handling", False):
            temperature = config.get("temperature")
            if temperature is not None and not (0 <= float(temperature) <= 2):
                raise ValueError(
                    "Temperature must be between 0 and 2 or NULL for o1-preview models"
                )

        max_tokens = config.get("max_tokens", None)
        if max_tokens is not None and int(max_tokens) <= 0:
            raise ValueError("Max tokens must be a positive integer.")

        max_completion_tokens = config.get("max_completion_tokens")
        if max_completion_tokens is not None:
            try:
                max_completion_tokens = int(max_completion_tokens)
                if not (1 <= max_completion_tokens <= 16384):
                    raise ValueError(
                        "max_completion_tokens must be between 1 and 16384"
                    )
                config["max_completion_tokens"] = max_completion_tokens
            except (TypeError, ValueError):
                raise ValueError("max_completion_tokens must be a valid integer")

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
