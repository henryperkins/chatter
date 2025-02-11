"""Database module for the application.

Merged with missing functionality from the provided snippet. Key additions include:
• mark_initialized() function
• test_db_connection() function
• db_transaction() context manager
• check_open_transactions() helper
• Extended connect_args in create_db_engine()
• Additional environment-based settings for create_engine()

Existing code has been preserved where possible, with new features merged in.
"""

import os
import logging
import json
import datetime
from typing import Optional, TypeVar, Callable, Any, Dict, Union, cast, Iterator, List
from contextlib import contextmanager

from flask import current_app, Flask
import click

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

from logging_config import get_logger

logger = get_logger(__name__)

# Type variables and aliases
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
DbState = Dict[str, Union[Engine, scoped_session, bool, None]]
SessionFactory = scoped_session

# Mark initialization state
_initialized = False


def mark_initialized() -> None:
    """Mark the database as initialized (from the snippet)."""
    global _initialized
    _initialized = True


def test_db_connection() -> None:
    """
    Test database connection by executing a simple query (from the snippet).
    Uses a fresh session to avoid any existing transaction state.
    """
    try:
        db_state = get_db_state()
        session_factory = cast(Optional[SessionFactory], db_state.get("Session"))
        if not session_factory:
            raise RuntimeError("Session factory is not initialized")

        session = session_factory()
        try:
            result = session.execute(text("SELECT 1"))
            value = result.scalar()
            if value == 1:
                logger.info("Database connection test successful")
            else:
                logger.error("Database connection test failed - unexpected result")
        finally:
            session.close()
    except Exception as e:
        logger.error("Database connection test failed: %s", str(e))
        raise


# Connection pool settings
POOL_SETTINGS = {
    "POOL_SIZE": int(os.getenv("DB_POOL_SIZE", "15")),
    "MAX_OVERFLOW": int(os.getenv("DB_MAX_OVERFLOW", "30")),
    "POOL_TIMEOUT": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    "POOL_PRE_PING": True,  # Always check connection before using
    "POOL_RECYCLE": int(os.getenv("DB_POOL_RECYCLE", "3600")),
}


def create_db_engine(db_uri: str) -> Engine:
    """
    Create SQLAlchemy engine with optimized settings.
    """
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
        connect_args={
            "connect_timeout": 60,
            "keepalives": 1,
            "keepalives_idle": 120,
            "keepalives_interval": 30,
            "keepalives_count": 15,
            "application_name": "chatter-app",
            "options": "-c statement_timeout=120000 -c idle_in_transaction_session_timeout=240000"
        },
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


@with_db_retries()
def execute_statement(
    db: Session, statement: str, params: Optional[Dict[str, Any]] = None
) -> CursorResult[Row[Any]]:
    """Execute a SQL statement with error handling."""
    import time  # For timing measurements
    logger.debug("Executing SQL statement: %s", statement[:200])  # Truncated log
    try:
        start_time = time.perf_counter()
        with db.begin():
            result = db.execute(text(statement), params or {})
            duration = time.perf_counter() - start_time
            logger.info("SQL executed [%0.3f seconds]", duration)
            return result
    except SQLAlchemyError as e:
        logger.error(
            "DB error in statement: %s\nParams: %s",
            statement,
            str(params)[:500],
            exc_info=True
        )
        raise RuntimeError(f"Database operation failed: {str(e)}") from e


def get_db_state(app: Optional[Flask] = None) -> DbState:
    """Get database state dictionary."""
    if not app:
        app = current_app
    if not app:
        return {"engine": None, "Session": None, "initialized": False}

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
def db_session(app: Optional[Flask] = None, transactional: bool = False) -> Iterator[Session]:
    """
    Unified database session context manager supporting optional transactional mode.
    Existing usage retained, but we do not override snippet's approach.
    """
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


@contextmanager
def db_transaction(app: Optional[Flask] = None) -> Iterator[Session]:
    """
    Provide a transactional scope that remains open until explicit commit/rollback (from snippet).
    """
    db_state = get_db_state(app)
    session_factory = db_state["Session"]
    if not session_factory:
        raise RuntimeError("Database not initialized")

    session = session_factory()
    try:
        session.begin()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_default_model(db: Session) -> Optional[int]:
    """
    Create default provider and model if they don't exist.
    Moved from existing code, references config.py for encryption.
    """
    from models import Model
    from config import Config

    # Check if default model exists using raw SQL
    result = db.execute(text("SELECT COUNT(*) FROM models WHERE is_default = TRUE"))
    if result.scalar() > 0:
        return None

    try:
        # Check if provider exists
        provider = db.execute(
            text("SELECT id, is_azure FROM providers WHERE slug = 'azure-openai'")
        ).mappings().first()

        if provider:
            db.execute(
                text("UPDATE providers SET is_azure = TRUE WHERE id = :id"),
                {"id": provider["id"]},
            )
            db.commit()
            provider_id = provider["id"]
        else:
            # Create new provider
            config_instance = Config()  # create a Config instance
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
                "api_base_url": config_instance.AZURE_API_ENDPOINT.rstrip("/"),
                "validation_rules": json.dumps({
                    "model_id": "^[a-zA-Z0-9-]{3,64}$",
                    "api_version": "^\\d{4}-\\d{2}-\\d{2}(-preview)?$",
                }),
                "capabilities": json.dumps(config_instance.MODEL_CAPABILITIES),
            })
            provider_id = result.scalar()
            db.commit()

        # Encrypt API key
        try:
        
            from utils.encryption import encrypt_api_key
            config_instance = Config()
            api_key = encrypt_api_key(config_instance.AZURE_OPENAI_KEY, config_instance.ENCRYPTION_KEY)
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}")
            raise ValueError("Failed to encrypt API key")

        # Build model data
        model_data = {
            "provider_id": provider_id,
            "name": config_instance.DEFAULT_MODEL_NAME,
            "deployment_name": config_instance.AZURE_DEPLOYMENT_NAME,
            "description": "Azure OpenAI o1 model",
            "api_endpoint": config_instance.DEFAULT_API_ENDPOINT.rstrip("/"),
            "api_key": api_key,
            "api_version": config_instance.AZURE_API_VERSION,
            "temperature": config_instance.DEFAULT_TEMPERATURE,
            "max_tokens": int(config_instance.DEFAULT_MAX_TOKENS),
            "max_completion_tokens": config_instance.DEFAULT_MAX_COMPLETION_TOKENS,
            "model_type": config_instance.DEFAULT_MODEL_TYPE,
            "reasoning_effort": config_instance.DEFAULT_REASONING_EFFORT,
            "requires_o1_handling": config_instance.DEFAULT_REQUIRES_O1_HANDLING,
            "supports_streaming": False,  # o1 models don't support streaming
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


def check_open_transactions() -> List[Dict[str, Any]]:
    """
    Check for open transactions that might be stuck (from snippet).
    """
    try:
        with db_session() as session:
            result = session.execute(text("""
                SELECT pid,
                       age(clock_timestamp(), query_start) as duration,
                       state, query, application_name
                FROM pg_stat_activity
                WHERE state = 'idle in transaction'
                  AND datname = current_database()
                  AND age(clock_timestamp(), query_start) > interval '1 minute'
            """))
            return [dict(row) for row in result.mappings()]
    except Exception as e:
        logger.error(f"Failed to check open transactions: {str(e)}")
        return []


def check_db_health() -> Dict[str, Any]:
    """
    Perform comprehensive database health check by checking pool stats,
    blocked queries, replication (if any), long-running queries, etc. (from snippet).
    """
    health_status = {
        "status": "healthy",
        "details": {},
        "errors": [],
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }

    try:
        with db_session() as session:
            # Basic connectivity check
            result = session.execute(text("SELECT 1"))
            if result.scalar() != 1:
                health_status["status"] = "unhealthy"
                health_status["errors"].append("Basic connectivity check failed")

            # Pool stats
            conn = session.connection().connection
            pool_stats = {
                "checked_out": conn.pool.checkedout(),
                "checked_in": conn.pool.checkedin(),
                "overflow": conn.pool.overflow(),
                "size": conn.pool.size(),
                "max_overflow": conn.pool.max_overflow(),
                "timeout": conn.pool.timeout(),
                "recycle": conn.pool.recycle(),
            }
            health_status["details"]["pool"] = pool_stats

            # Blocked queries
            result = session.execute(text("""
                SELECT COUNT(*)
                FROM pg_stat_activity
                WHERE wait_event_type = 'Lock'
                  AND datname = current_database()
            """))
            blocked_queries = result.scalar()
            if blocked_queries > 0:
                health_status["status"] = "degraded"
                health_status["details"]["blocked_queries"] = blocked_queries

            # Attempt replication status
            try:
                result = session.execute(text("""
                    SELECT state, sync_state
                    FROM pg_stat_replication
                """))
                replication_status = [dict(row) for row in result.mappings()]
                if replication_status:
                    health_status["details"]["replication"] = replication_status
            except Exception:
                pass  # Not a replication setup

            # Long-running queries
            result = session.execute(text("""
                SELECT pid,
                       age(clock_timestamp(), query_start) as duration,
                       state,
                       query
                FROM pg_stat_activity
                WHERE state != 'idle'
                  AND datname = current_database()
                  AND age(clock_timestamp(), query_start) > interval '30 seconds'
            """))
            long_running = [dict(row) for row in result.mappings()]
            if long_running:
                health_status["status"] = "degraded"
                health_status["details"]["long_running"] = long_running

            # Database size
            result = session.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database()))
            """))
            health_status["details"]["size"] = result.scalar()

            # Connection stats
            result = session.execute(text("""
                SELECT state, count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                GROUP BY state
            """))
            health_status["details"]["connections"] = dict(result.fetchall())

            # Check open transactions
            open_transactions = check_open_transactions()
            if open_transactions:
                health_status["status"] = "degraded"
                health_status["details"]["open_transactions"] = open_transactions
                logger.warning(f"Found {len(open_transactions)} open transactions")

    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["errors"].append(f"Health check failed: {str(e)}")
        logger.error(f"Database health check failed: {str(e)}", exc_info=True)

    return health_status


def init_db() -> None:
    """
    Initialize the database schema by dropping all existing tables and recreating them.
    Existing approach retained, but close_db is called separately.
    """
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
                DROP TABLE IF EXISTS model_versions CASCADE;
                DROP TABLE IF EXISTS login_attempts CASCADE;
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

        # Attempt default model creation
        with db_session() as db:
            create_default_model(db)
            logger.info("Default model creation completed")

        # Mark as initialized
        mark_initialized()
        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise


def init_app(app: Flask) -> None:
    """Initialize database for the Flask application, consistent with snippet's approach."""
    global _initialized
    if _initialized:
        return

    logger.info("Initializing database with init_app(app)")

    if not hasattr(app, "_db_state"):
        app._db_state = {"engine": None, "Session": None, "initialized": False, "initializing": True}

    try:
        logger.info("Creating database engine with URI: %s", app.config["DATABASE_URI"])
        app._db_state["engine"] = create_db_engine(app.config["DATABASE_URI"])
        engine = app._db_state["engine"]
        logger.info("Database engine created successfully")

        # Verify connection using raw connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()

        # Create custom session class
        class CustomSession(Session):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault('autocommit', False)
                kwargs.setdefault('autoflush', False)
                super().__init__(*args, **kwargs)

        # Create session factory
        session_factory = sessionmaker(
            class_=CustomSession,
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            twophase=False,
            info={"isolation_level": "READ COMMITTED", "autoflush": False},
        )
        app._db_state["Session"] = scoped_session(session_factory)
        app._db_state["initialized"] = True
        _initialized = True

        logger.info("Database initialized and verified for app %s", app.name)

    except Exception as e:
        app._db_state["initialized"] = False
        logger.error("Database initialization failed for app %s: %s", app.name, str(e))
        raise


def close_db(e: Optional[BaseException] = None) -> None:
    """Clean up database resources."""
    global _initialized
    db_state = get_db_state()

    if not _initialized or not db_state.get("initialized"):
        return

    logger.info("Initiating proper database shutdown")

    try:
        if engine := db_state.get("engine"):
            logger.info(f"Disposing engine with {engine.pool.status()}")
            engine.dispose()
            logger.info("Engine pool cleared")

        db_state.update({"initialized": False, "initializing": False})
        _initialized = False

    except Exception:
        logger.error("Error during database shutdown", exc_info=True)


def init_db_command() -> None:
    """
    Flask CLI command to initialize database (from snippet).
    We wrap init_db() in a click command for convenience.
    """
    try:
        init_db()
        click.echo("Initialized the database.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise click.ClickException(f"Database initialization failed: {str(e)}")
