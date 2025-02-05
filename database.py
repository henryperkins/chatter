"""Database module for the application."""

import os
import logging
from typing import Optional, TypeVar, Callable, Any, Dict, Union, cast, Iterator, List
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, CursorResult, Row
from sqlalchemy.exc import OperationalError, SQLAlchemyError, InterfaceError
from sqlalchemy.orm import scoped_session, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
    before_sleep_log,
)
from flask import g, current_app, Flask
import click
import json
import datetime
from cryptography.fernet import Fernet
import base64
import hashlib

from config import Config
from logging_config import get_logger

logger = get_logger(__name__)

# Type variables and aliases
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
DbState = Dict[str, Union[Engine, scoped_session, bool, None]]
SessionFactory = scoped_session

_initialized = False

POOL_SETTINGS = {
    "POOL_SIZE": int(os.getenv("DB_POOL_SIZE", "5")),
    "MAX_OVERFLOW": int(os.getenv("DB_MAX_OVERFLOW", "10")),
    "POOL_TIMEOUT": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    "POOL_PRE_PING": os.getenv("DB_POOL_PRE_PING", "false").lower() == "true",
    "POOL_RECYCLE": int(os.getenv("DB_POOL_RECYCLE", "1800")),
}


def create_db_engine(db_uri: str) -> Engine:
    """Create SQLAlchemy engine with optimized settings."""
    return create_engine(
        db_uri,
        future=True,
        poolclass=QueuePool,
        pool_size=POOL_SETTINGS["POOL_SIZE"],
        max_overflow=POOL_SETTINGS["MAX_OVERFLOW"],
        pool_timeout=POOL_SETTINGS["POOL_TIMEOUT"],
        pool_pre_ping=POOL_SETTINGS["POOL_PRE_PING"],
        pool_recycle=POOL_SETTINGS["POOL_RECYCLE"],
        pool_use_lifo=True,
        isolation_level="READ COMMITTED",
        execution_options={"autocommit": False},
        connect_args={"sslmode": "require"},
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    )


def with_db_retries(
    max_attempts: int = 3, wait_seconds: float = 0.5
) -> Callable[[F], F]:
    """Decorator for database operation retries."""

    def decorator(func: F) -> F:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_fixed(wait_seconds),
            retry=retry_if_exception_type((OperationalError, InterfaceError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except (OperationalError, InterfaceError) as e:
                logger.warning(f"Database operation failed, retrying: {str(e)}")
                raise
            except SQLAlchemyError as e:
                logger.error(f"Database error: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                raise

        return cast(F, wrapper)

    return decorator


def get_db_state(app: Optional[Flask] = None) -> DbState:
    """Get database state dictionary."""
    if not app:
        app = current_app
    if not hasattr(app, "_db_state"):
        app._db_state = {"engine": None, "Session": None, "initialized": False}
    return app._db_state


def is_initialized() -> bool:
    """Check if database is properly initialized."""
    if not current_app:
        return False
    db_state = get_db_state()
    return all(
        [
            db_state.get("engine") is not None,
            db_state.get("Session") is not None,
            db_state.get("initialized", False) is True,
        ]
    )


@contextmanager
def db_session(
    app: Optional[Flask] = None, transactional: bool = False
) -> Iterator[Session]:
    """Unified database session context manager supporting transactional mode."""
    db_state = get_db_state(app)
    session_factory = db_state["Session"]
    if not session_factory:
        raise RuntimeError("Database not initialized")
    session = session_factory()
    try:
        if transactional:
            session.begin()
        yield session
        if transactional:
            session.commit()
    except Exception:
        if transactional:
            session.rollback()
        raise
    finally:
        session.close()


@with_db_retries()
def execute_statement(
    db: Session, statement: str, params: Optional[Dict[str, Any]] = None
) -> CursorResult[Row[Any]]:
    """Execute a SQL statement with error handling."""
    try:
        with db.begin():
            return db.execute(text(statement), params or {})
    except SQLAlchemyError as e:
        raise RuntimeError(f"Database operation failed: {str(e)}") from e


def create_default_model(db: Session) -> Optional[int]:
    """Create default provider and model if they don't exist."""
    from models import Model, Provider
    from config import Config

    # Check if default model exists using raw SQL
    result = db.execute(text("SELECT COUNT(*) FROM models WHERE is_default = TRUE")).scalar()
    if result > 0:
        return None

    try:
        # Check if provider exists
        provider = db.execute(
            text("SELECT id, is_azure FROM providers WHERE slug = 'azure-openai'")
        ).mappings().first()

        if provider:
            # Update existing provider
            db.execute(
                text("UPDATE providers SET is_azure = TRUE WHERE id = :id"),
                {"id": provider["id"]}
            )
            db.commit()
            provider_id = provider["id"]
        else:
            # Create new provider
            result = db.execute(text("""
                INSERT INTO providers (
                    name, slug, api_base_url, requires_authentication,
                    api_version_format, endpoint_pattern, auth_type,
                    validation_rules, capabilities, is_azure
                ) VALUES (
                    'Azure OpenAI',
                    'azure-openai',
                    :api_base_url,
                    TRUE,
                    'YYYY-MM-DD',
                    'https://{endpoint}/openai/deployments/{deployment}/chat/completions',
                    'api-key',
                    :validation_rules,
                    :capabilities,
                    TRUE
                ) RETURNING id
            """), {
                "api_base_url": Config().AZURE_API_ENDPOINT.rstrip("/"),
                "validation_rules": json.dumps({
                    "model_id": "^[a-zA-Z0-9-]{3,64}$",
                    "api_version": "^\\d{4}-\\d{2}-\\d{2}(-preview)?$",
                }),
                "capabilities": json.dumps(Config().MODEL_CAPABILITIES)
            })
            provider_id = result.scalar()
            db.commit()

        config_instance = Config()  # create a Config instance
        key_bytes = hashlib.sha256(config_instance.ENCRYPTION_KEY.encode()).digest()
        encryption_key = base64.b64encode(key_bytes).decode()
        cipher_suite = Fernet(encryption_key.encode())
        encrypted_api_key = cipher_suite.encrypt(config_instance.AZURE_OPENAI_KEY.encode()).decode()

        config = Config()  # Create config instance
        model_data = {
            "provider_id": provider_id,
            "name": config.MODEL_NAME,
            "deployment_name": config.DEFAULT_DEPLOYMENT_NAME,
            "description": "Azure OpenAI GPT-4 model with streaming support",
            "api_endpoint": config.DEFAULT_API_ENDPOINT.rstrip("/"),
            "api_key": encrypted_api_key,
            "api_version": config.AZURE_API_VERSION,
            "temperature": config.DEFAULT_TEMPERATURE,
            "max_tokens": 128000,
            "max_completion_tokens": min(config.MAX_TOKENS, 16384),
            "model_type": "azure",
            "requires_o1_handling": False,
            "supports_streaming": True,
            "is_default": True
        }
        Model.validate_model_config(model_data)
        model_id = Model.create(model_data)
        logger.info("Default model created successfully")
        return model_id

    except Exception as e:
        logger.error(f"Failed to create default model: {str(e)}")
        db.rollback()
        raise


def init_db() -> None:
    """Initialize the database schema by dropping all existing tables and recreating them."""
    try:
        # Get the schema file path
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        
        # Read schema file
        with open(schema_path) as f:
            schema = f.read()
            
        # Execute schema with drop statements first
        with db_session() as db:
            # Check existing tables
            result = db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            existing_tables = [row[0] for row in result]
            if existing_tables:
                logger.info(f"Found existing tables: {', '.join(existing_tables)}")
            
            # Drop all existing tables in reverse dependency order
            db.execute(text("""
                DROP TABLE IF EXISTS uploaded_files CASCADE;
                DROP TABLE IF EXISTS messages CASCADE;
                DROP TABLE IF EXISTS chats CASCADE;
                DROP TABLE IF EXISTS models CASCADE;
                DROP TABLE IF EXISTS providers CASCADE;
                DROP TABLE IF EXISTS users CASCADE;
            """))
            db.commit()
            
            # Verify tables were dropped
            result = db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            remaining_tables = [row[0] for row in result]
            if remaining_tables:
                logger.warning(f"Tables remaining after drop: {', '.join(remaining_tables)}")
            else:
                logger.info("All tables successfully dropped")
            
            # Now create fresh schema
            db.execute(text(schema))
            db.commit()
            
            # Verify new tables
            result = db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            new_tables = [row[0] for row in result]
            logger.info(f"Fresh tables created: {', '.join(new_tables)}")
            
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

def init_app(app: Flask) -> None:
    """Initialize database for the Flask application."""
    global _initialized
    if _initialized:
        return

    if not hasattr(app, "_db_state"):
        app._db_state = {"engine": None, "Session": None, "initialized": False}

    try:
        app._db_state["engine"] = create_db_engine(app.config["DATABASE_URI"])

        session_factory = sessionmaker(
            bind=app._db_state["engine"],
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        app._db_state["Session"] = scoped_session(session_factory)

        with app._db_state["engine"].connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()

        app._db_state["initialized"] = True
        _initialized = True
        logger.info("Database initialized successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise


def close_db(e: Optional[BaseException] = None) -> None:
    """Clean up database resources."""
    global _initialized
    db_state = get_db_state()

    if not _initialized or not db_state.get("initialized"):
        return

    try:
        if engine := db_state.get("engine"):
            engine.dispose()
        db_state.update({"initialized": False, "initializing": False})
        _initialized = False
    except Exception as e:
        logger.error(f"Error during database shutdown: {str(e)}")


def check_db_health() -> Dict[str, Any]:
    """Check database health status."""
    health_data = {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "details": {},
    }

    try:
        with db_session() as session:
            session.execute(text("SELECT 1")).scalar()
            conn = session.connection().connection
            health_data["details"]["pool"] = {
                "size": conn.pool.size(),
                "checked_out": conn.pool.checkedout(),
                "checked_in": conn.pool.checkedin(),
                "overflow": conn.pool.overflow(),
            }
            for query, key in [
                (
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'",
                    "locked_queries",
                ),
                (
                    "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction' AND age(clock_timestamp(), query_start) > interval '1 minute'",
                    "stuck_transactions",
                ),
            ]:
                count = session.execute(text(query)).scalar()
                if count > 0:
                    health_data["status"] = "degraded"
                    health_data["details"][key] = count

        return health_data

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "error": str(e),
        }
