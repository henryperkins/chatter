"""
Database module for the application.
"""

import os
import logging
import json
import datetime
from typing import (
    Optional,
    TypeVar,
    Callable,
    Any,
    Dict,
    Union,
    cast,
    Iterator,
    List,
)
from contextlib import contextmanager

from flask import current_app, Flask
import click

from flask_sqlalchemy import SQLAlchemy
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

from config import Config
from logging_config import get_logger

from models.model import Model  # Needed in create_default_model
logger = get_logger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
DbState = Dict[str, Union[Engine, scoped_session, bool, None]]
SessionFactory = scoped_session

_initialized = False

POOL_SETTINGS = {
    "POOL_SIZE": int(os.getenv("DB_POOL_SIZE", "15")),
    "MAX_OVERFLOW": int(os.getenv("DB_MAX_OVERFLOW", "30")),
    "POOL_TIMEOUT": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    "POOL_PRE_PING": True,
    "POOL_RECYCLE": int(os.getenv("DB_POOL_RECYCLE", "3600")),
}

db = SQLAlchemy(engine_options=current_app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}))


def get_db_state(app: Optional[Flask] = None) -> DbState:
    if not app:
        app = current_app
    if not app:
        return {"engine": None, "Session": None, "initialized": False}
    db_state = app.extensions.setdefault("chatter-db", {
        "engine": None,
        "Session": None,
        "initialized": False,
    })
    return cast(DbState, db_state)


def mark_initialized() -> None:
    global _initialized
    _initialized = True
    db_state = get_db_state()
    db_state["initialized"] = True


def is_initialized() -> bool:
    db_state = get_db_state()
    return bool(db_state.get("initialized", False))


def create_db_engine(db_uri: str) -> Engine:
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
            "options": "-c statement_timeout=120000 "
                       "-c idle_in_transaction_session_timeout=240000",
            "sslmode": "require"
        },
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    )


def with_db_retries(
    max_attempts: int = 3,
    wait_seconds: float = 0.5
) -> Callable[[F], F]:
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
    db: Session,
    statement: str,
    params: Optional[Dict[str, Any]] = None
) -> CursorResult[Row[Any]]:
    import time
    logger.debug("Executing SQL statement: %s", statement[:200])
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


def test_db_connection() -> None:
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


@contextmanager
def db_session(app: Optional[Flask] = None, transactional: bool = False) -> Iterator[Session]:
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
    Create a default model if it doesn't exist.
    """
    # Check if a default model already exists
    result = db.execute(text("SELECT COUNT(*) FROM models WHERE is_default = TRUE"))
    if result.scalar() > 0:
        return None

    try:
        from config import Config
        config_instance = Config()

        from models.provider import Provider

        # Check if provider exists
        provider = Provider.get_by_slug(db, 'azure-openai')
        if provider:
            if not provider.is_azure:
                provider.is_azure = True
                db.commit()
            provider_id = provider.id
        else:
            # Create new provider using raw SQL or ORM
            result = db.execute(text("""
                INSERT INTO providers (
                    name, slug, api_base_url, requires_authentication,
                    api_version_format, endpoint_pattern, auth_type,
                    validation_rules, capabilities, is_azure, is_active
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
                    TRUE,
                    TRUE
                ) RETURNING id
            """), {
                "api_base_url": config_instance.AZURE_OPENAI_ENDPOINT.rstrip("/"),
                "validation_rules": json.dumps({
                    "model_id": "^[a-zA-Z0-9-]{3,64}$",
                    "api_version": "^\\d{4}-\\d{2}-\\d{2}(-preview)?$",
                }),
                "capabilities": json.dumps(config_instance.MODEL_CAPABILITIES),
            })
            provider_id = result.scalar()
            db.commit()

        from utils.encryption import encrypt_api_key
        if not config_instance.AZURE_OPENAI_KEY or not config_instance.ENCRYPTION_KEY:
            raise ValueError("Missing API or ENCRYPTION key in config.")
        api_key = encrypt_api_key(
            config_instance.AZURE_OPENAI_KEY,
            config_instance.ENCRYPTION_KEY
        )

        model_data = {
            "provider_id": provider_id,
            "name": config_instance.DEFAULT_MODEL_NAME,
            "deployment_name": config_instance.AZURE_OPENAI_DEPLOYMENT_NAME,
            "description": "Azure OpenAI o1 model",
            "api_endpoint": config_instance.DEFAULT_API_ENDPOINT.rstrip("/"),
            "api_key": api_key,
            "api_version": config_instance.AZURE_OPENAI_API_VERSION,
            "temperature": config_instance.DEFAULT_TEMPERATURE,
            "max_tokens": int(config_instance.DEFAULT_MAX_TOKENS),
            "max_completion_tokens": config_instance.DEFAULT_MAX_COMPLETION_TOKENS,
            "model_type": config_instance.DEFAULT_MODEL_TYPE,
            "reasoning_effort": config_instance.DEFAULT_REASONING_EFFORT,
            "requires_o1_handling": config_instance.DEFAULT_REQUIRES_O1_HANDLING,
            "supports_streaming": False,
            "is_default": True,
        }

        # Validate the model config with the session
        Model.validate_model_config(model_data, db)

        # Now actually create the record
        model_id = Model.create(db, model_data)
        logger.info("Default model created successfully with ID %s", model_id)
        return model_id

    except Exception as e:
        logger.error(f"Failed to create default model: {str(e)}")
        db.rollback()
        raise


def check_open_transactions() -> List[Dict[str, Any]]:
    try:
        with db_session() as session:
            result = session.execute(text("""
                SELECT pid,
                       age(clock_timestamp(), query_start) as duration,
                       state,
                       query,
                       application_name
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
    health_status = {
        "status": "healthy",
        "details": {},
        "errors": [],
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }

    try:
        with db_session() as session:
            # Basic connectivity
            result = session.execute(text("SELECT 1"))
            if result.scalar() != 1:
                health_status["status"] = "unhealthy"
                health_status["errors"].append("Basic connectivity check failed")

            engine = session.get_bind()
            pool_stats = {
                "checked_out": engine.pool.checkedout(),
                "checked_in": engine.pool.checkedin(),
                "overflow": engine.pool.overflow(),
                "size": engine.pool.size(),
                "max_overflow": engine.pool.max_overflow(),
                "timeout": engine.pool.timeout(),
                "recycle": engine.pool.recycle(),
            }
            health_status["details"]["pool"] = pool_stats

            blocked_queries = session.execute(text("""
                SELECT COUNT(*)
                FROM pg_stat_activity
                WHERE wait_event_type = 'Lock'
                  AND datname = current_database()
            """)).scalar()
            if blocked_queries and blocked_queries > 0:
                health_status["status"] = "degraded"
                health_status["details"]["blocked_queries"] = blocked_queries

            # Replication status (ignore if not present)
            try:
                rep_result = session.execute(text("""
                    SELECT state, sync_state
                    FROM pg_stat_replication
                """))
                replication_status = [dict(row) for row in rep_result.mappings()]
                if replication_status:
                    health_status["details"]["replication"] = replication_status
            except Exception:
                pass

            long_running = session.execute(text("""
                SELECT pid,
                       age(clock_timestamp(), query_start) AS duration,
                       state,
                       query
                FROM pg_stat_activity
                WHERE state != 'idle'
                  AND datname = current_database()
                  AND age(clock_timestamp(), query_start) > interval '30 seconds'
            """)).mappings().all()
            if long_running:
                health_status["status"] = "degraded"
                health_status["details"]["long_running"] = [dict(row) for row in long_running]

            db_size = session.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database()))
            """)).scalar()
            health_status["details"]["size"] = db_size

            conn_stats = session.execute(text("""
                SELECT state, count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                GROUP BY state
            """)).all()
            health_status["details"]["connections"] = dict(conn_stats)

            open_txs = check_open_transactions()
            if open_txs:
                health_status["status"] = "degraded"
                health_status["details"]["open_transactions"] = open_txs
                logger.warning(f"Found {len(open_txs)} open transactions")

    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["errors"].append(f"Health check failed: {str(e)}")
        logger.error(f"Database health check failed: {str(e)}", exc_info=True)

    return health_status


def init_db() -> None:
    from models.base import Base
    from models.login_attempt import LoginAttempt
    from sqlalchemy import MetaData

    try:
        db_state = get_db_state()
        engine = db_state["engine"]
        if not engine:
            raise RuntimeError("Database engine not initialized")

        # Attempt to ensure certain columns exist
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE providers ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT TRUE")
                )
        except Exception:
            pass

        meta = MetaData()
        meta.reflect(bind=engine)
        meta.drop_all(bind=engine)

        Base.metadata.create_all(bind=engine)

        # Create a default model if needed
        with db_session(transactional=True) as dbs:
            create_default_model(dbs)

        mark_initialized()
        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise


def init_app(app: Flask) -> None:
    db_state = get_db_state(app)
    if db_state["initialized"]:
        logger.debug("Database is already initialized; skipping init_app.")
        return

    logger.info("Initializing database with init_app(app)")

    try:
        db_state["engine"] = create_db_engine(app.config["DATABASE_URI"])
        engine = db_state["engine"]
        logger.info("Database engine created successfully with URI: %s", app.config["DATABASE_URI"])

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()

        from sqlalchemy.orm import Session

        class CustomSession(Session):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("autocommit", False)
                kwargs.setdefault("autoflush", False)
                super().__init__(*args, **kwargs)

        session_factory = sessionmaker(
            class_=CustomSession,
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            twophase=False,
            info={"isolation_level": "READ COMMITTED", "autoflush": False},
        )
        db_state["Session"] = scoped_session(session_factory)
        db_state["initialized"] = True
        mark_initialized()

        logger.info("Database initialized and verified for app: %s", app.name)

    except Exception as e:
        db_state["initialized"] = False
        logger.error("Database initialization failed for app %s: %s", app.name, str(e))
        raise


def close_db(e: Optional[BaseException] = None) -> None:
    db_state = get_db_state()
    if not db_state["initialized"]:
        return

    logger.info("Initiating proper database shutdown")
    try:
        engine = db_state.get("engine")
        if engine:
            logger.info(f"Disposing engine with pool status: {engine.pool.status()}")
            engine.dispose()
            logger.info("Engine pool cleared")

        db_state["initialized"] = False
        global _initialized
        _initialized = False

    except Exception:
        logger.error("Error during database shutdown", exc_info=True)


@click.command("init-db")
def init_db_command() -> None:
    try:
        init_db()
        click.echo("Initialized the database.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise click.ClickException(f"Database initialization failed: {str(e)}")
