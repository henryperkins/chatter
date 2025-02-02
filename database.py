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

# Track initialization state
_initialized = False

def mark_initialized() -> None:
    """Mark the database as initialized."""
    global _initialized
    _initialized = True

def test_db_connection():
    """Test database connection by executing a simple query."""
    try:
        # Use a fresh session to avoid any existing transaction state
        db_state = get_db_state()
        session_factory = cast(Optional[SessionFactory], db_state.get("Session"))
        if not session_factory:
            raise RuntimeError("Session factory is not initialized")

        session = session_factory()
        try:
            # Execute test query without starting a transaction
            result = session.execute(text("SELECT 1"))
            value = result.scalar()
            if value == 1:
                logger.info("Database connection test successful")
            else:
                logger.error("Database connection test failed - unexpected result")
        finally:
            # Ensure session is closed
            session.close()
    except Exception as e:
        logger.error("Database connection test failed: %s", str(e))
        raise


logger = logging.getLogger(__name__)

# Type variables
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])

# Type aliases
DbState = Dict[str, Union[Engine, scoped_session, bool, None]]
SessionFactory = scoped_session

# Connection pool settings with environment variable fallbacks
POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_PRE_PING: bool = os.getenv("DB_POOL_PRE_PING", "false").lower() == "true"  # Disable pre-ping
POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30 minutes

def create_db_engine(db_uri: str) -> Engine:
    """Create SQLAlchemy engine with PostgreSQL-optimized settings."""
    engine = create_engine(
        db_uri,
        future=True,  # Enable 2.0-style transaction behavior
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_pre_ping=POOL_PRE_PING,
        pool_recycle=POOL_RECYCLE,
        pool_use_lifo=True,  # Better connection reuse
        isolation_level="READ COMMITTED",
        execution_options={"autocommit": False},  # Explicit transaction control
        # Remove connect_args to rely on URI parameters
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    )

    # Add event listeners for connection management

    return engine

def with_db_retries(
    max_attempts: int = 3, wait_seconds: float = 0.5
) -> Callable[[F], F]:
    """Decorator to retry database operations on failure."""
    def decorator(func: F) -> F:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_fixed(wait_seconds),
            retry=retry_if_exception_type((OperationalError, InterfaceError)),
            before_sleep=before_sleep_log(logger, logging.WARNING)
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
    """Execute a single SQL statement with error handling using SQLAlchemy 2.0 patterns."""
    try:
        with db.begin():
            return db.execute(text(statement), params or {})
    except SQLAlchemyError as e:
        raise RuntimeError(f"Database operation failed: {str(e)}") from e

def get_db_state(app: Optional[Flask] = None) -> Dict[str, Union[Engine, scoped_session, bool, None]]:
    """Get database state with explicit app reference"""
    if not app:
        from flask import current_app
        app = current_app if current_app else None

    if not app:
        return {"engine": None, "Session": None, "initialized": False}

    if not hasattr(app, "_db_state"):
        app._db_state = {
            "engine": None,
            "Session": None,
            "initialized": False
        }

    return app._db_state

def is_initialized() -> bool:
    """Check if database is properly initialized."""
    if not current_app:
        return False

    db_state = get_db_state()
    return (
        db_state.get("engine") is not None
        and db_state.get("Session") is not None
        and db_state.get("initialized", False) is True
    )

@contextmanager
def db_session(app: Optional[Flask] = None) -> Iterator[Session]:
    """Provide a database session scope."""
    db_state = get_db_state(app)
    session_factory = db_state["Session"]

    if not session_factory:
        raise RuntimeError("Database not initialized")

    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

@contextmanager
def db_transaction(app: Optional[Flask] = None) -> Iterator[Session]:
    """Provide a transactional scope that remains open until explicit commit/rollback"""
    db_state = get_db_state(app)
    session_factory = db_state["Session"]

    if not session_factory:
        raise RuntimeError("Database not initialized")

    session = session_factory()
    try:
        # Explicitly begin transaction
        session.begin()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(db_uri: Optional[str] = None) -> None:
    """Initialize PostgreSQL database with optimized settings."""
    try:
        if not current_app:
            raise RuntimeError(
                "Cannot initialize database outside of Flask application context"
            )

        db_uri = db_uri or current_app.config["DATABASE_URI"]
        if not db_uri:
            raise ValueError(
                "DATABASE_URI must be provided either directly or in app config"
            )

        # Get or create db state
        db_state = get_db_state()

        # Create fresh engine and store in state
        engine = create_db_engine(db_uri)
        db_state["engine"] = engine

        # Execute schema in a single transaction
        with engine.connect() as conn:
            # Execute schema.sql
            with current_app.open_resource("schema.sql") as f:
                schema_sql = f.read().decode("utf8")
                conn.execute(text(schema_sql))
                logger.debug("Schema SQL executed successfully")
            conn.commit()

        # Create default model after schema execution
        with db_session() as db:
            create_default_model(db)
            logger.info("Default model creation completed")

        # Configure session factory with explicit transaction control
        SessionLocal = scoped_session(
            sessionmaker(
                bind=engine,
                autoflush=False,
                expire_on_commit=False
            ),
            scopefunc=lambda: id(g) if hasattr(g, "_get_current_object") else None,
        )
        db_state["Session"] = SessionLocal
        db_state["initialized"] = True
        mark_initialized()

        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}", exc_info=True)
        raise RuntimeError(
            "Failed to initialize the database. Please check the database connection and try again."
        ) from e
    finally:
        # Ensure database connection is closed
        db_state = get_db_state()
        if db_state.get("engine"):
            db_state["engine"].dispose()
            logger.debug("Closed database engine connection")


def close_db(e: Optional[BaseException] = None) -> None:
    """Clean up database resources only at app teardown"""
    global _initialized
    db_state = get_db_state()

    if not _initialized or not db_state.get("initialized"):
        return

    logger.info("Initiating proper database shutdown")

    try:
        # Dispose engine but keep configuration
        if engine := db_state.get("engine"):
            logger.info(f"Disposing engine with {engine.pool.status()}")
            engine.dispose()
            logger.info("Engine pool cleared")

        # Reset initialization state without clearing config
        db_state.update({"initialized": False, "initializing": False})
        _initialized = False

    except Exception as e:
        logger.error(f"Error during database shutdown: {str(e)}", exc_info=True)


def init_db_command() -> None:
    """Flask CLI command to initialize database."""
    try:
        init_db()
        click.echo("Initialized the database.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise click.ClickException(f"Database initialization failed: {str(e)}")


def create_default_model(db: Session) -> Optional[int]:
    """Create default provider and model if they don't exist."""
    from models import Model, Provider
    from config import Config

    # Check if default model exists
    result = db.execute(text("SELECT COUNT(*) FROM models WHERE is_default = TRUE"))
    default_exists = result.scalar_one()
    if default_exists:
        return None

    try:
        logger.info("Creating default provider and model")

        # Check for existing Azure provider first
        existing_provider = db.execute(
            text("SELECT id FROM providers WHERE slug = 'azure-openai'")
        ).scalar()

        if existing_provider:
            provider_id = existing_provider
            logger.info("Using existing Azure OpenAI provider")
        else:
            # Create default provider
            default_provider = {
                "name": "Azure OpenAI",
                "slug": "azure-openai",
                "api_base_url": Config.AZURE_API_ENDPOINT.rstrip("/"),
                "api_version_format": "2024-12-01-preview",
                "auth_type": "api-key",
                "endpoint_pattern": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
                "validation_rules": json.dumps({
                    "model_id": "^[a-zA-Z0-9-]{3,64}$",
                    "api_version": "^\\d{4}-\\d{2}-\\d{2}(-preview)?$"
                }),
                "capabilities": json.dumps({
                    "azure": {
                        "supports_streaming": True,
                        "max_tokens": 16384,
                        "token_overhead": 3,
                        "endpoint_format": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
                        "api_version": "2024-12-01-preview",
                    },
                    "o1-preview": {
                        "fixed_temperature": True,
                        "streaming": False,
                        "max_tokens": 8300,
                        "token_overhead": 3,
                        "endpoint_format": "https://{endpoint}/openai/deployments/{deployment}/chat/completions",
                        "api_version": "2024-12-01-preview",
                    }
                }),
                "requires_authentication": True
            }

            # Insert provider and get ID
            provider_query = text("""
                INSERT INTO providers (
                    name, slug, api_base_url, api_version_format,
                    auth_type, endpoint_pattern, validation_rules,
                    capabilities, requires_authentication
                ) VALUES (
                    :name, :slug, :api_base_url, :api_version_format,
                    :auth_type, :endpoint_pattern, :validation_rules,
                    :capabilities, :requires_authentication
                )
                RETURNING id
            """)
            result = db.execute(provider_query, default_provider)
            provider_id = result.scalar_one()
            db.commit()  # Commit the provider creation
            logger.info(f"Created new Azure OpenAI provider with ID: {provider_id}")

        # Create default model with proper encryption
        from cryptography.fernet import Fernet
        import base64
        import hashlib

        # Ensure encryption key is properly formatted
        encryption_key = Config.ENCRYPTION_KEY
        try:
            # Validate it's proper base64
            base64.b64decode(encryption_key, validate=True)
        except Exception:
            # If not valid base64, properly encode it
            key_bytes = hashlib.sha256(encryption_key.encode()).digest()
            encryption_key = base64.b64encode(key_bytes).decode()

        # Create Fernet cipher with properly encoded key
        cipher_suite = Fernet(encryption_key.encode())
        
        # Encrypt API key
        try:
            encrypted_api_key = cipher_suite.encrypt(Config.AZURE_API_KEY.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}")
            raise ValueError("Failed to encrypt API key")

        # Build API endpoint with deployment path
        api_endpoint = Config.DEFAULT_API_ENDPOINT.rstrip("/")
        deployment_name = "o1-preview"
        api_endpoint = f"{api_endpoint}/openai/deployments/{deployment_name}/chat/completions?api-version={Config.DEFAULT_API_VERSION}"

        # Determine model type and appropriate max_completion_tokens
        model_type = "azure"  # Default model type
        max_completion_tokens = Config.DEFAULT_MAX_COMPLETION_TOKENS
        requires_o1_handling = Config.DEFAULT_REQUIRES_O1_HANDLING

        default_model = {
            "name": Config.DEFAULT_MODEL_NAME,
            "deployment_name": deployment_name,
            "description": Config.DEFAULT_MODEL_DESCRIPTION,
            "provider_id": provider_id,
            "api_endpoint": api_endpoint,
            "api_key": encrypted_api_key,
            "model_type": "azure",
            "temperature": Config.DEFAULT_TEMPERATURE,
            "max_tokens": Config.DEFAULT_MAX_TOKENS,
            "max_completion_tokens": max_completion_tokens,
            "is_default": True,
            "requires_o1_handling": Config.DEFAULT_REQUIRES_O1_HANDLING,
            "supports_streaming": Config.DEFAULT_SUPPORTS_STREAMING,
            "api_version": Config.DEFAULT_API_VERSION,
        }

        # Validate model configuration
        from models.model import Model
        Model.validate_model_config(default_model)

        # Insert model
        model_query = text("""
            INSERT INTO models (
                provider_id, name, deployment_name, description, api_endpoint, api_key,
                api_version, temperature, max_tokens, max_completion_tokens,
                model_type, requires_o1_handling, supports_streaming, is_default
            ) VALUES (
                :provider_id, :name, :deployment_name, :description, :api_endpoint, :api_key,
                :api_version, :temperature, :max_tokens, :max_completion_tokens,
                :model_type, :requires_o1_handling, :supports_streaming, :is_default
            )
            RETURNING id
        """)
        result = db.execute(model_query, default_model)
        model_id = result.scalar_one()
        db.commit()  # Commit the model creation
        
        logger.info("Default provider and model created successfully")
        return model_id

    except Exception as e:
        logger.error(f"Failed to create default provider and model: {e}", exc_info=True)
        raise


def check_open_transactions() -> List[Dict[str, Any]]:
    """Check for open transactions that might be stuck."""
    try:
        with db_session() as session:
            result = session.execute(
                text(
                    """
                SELECT pid, age(clock_timestamp(), query_start) as duration,
                       state, query, application_name
                FROM pg_stat_activity
                WHERE state = 'idle in transaction'
                AND datname = current_database()
                AND age(clock_timestamp(), query_start) > interval '1 minute'
            """
                )
            )
            return [dict(row) for row in result.mappings()]
    except Exception as e:
        logger.error(f"Failed to check open transactions: {str(e)}")
        return []


def check_db_health() -> Dict[str, Any]:
    """Perform comprehensive database health check."""
    health_status = {
        "status": "healthy",
        "details": {},
        "errors": [],
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }

    try:
        with db_session() as session:
            # Check database connectivity
            result = session.execute(text("SELECT 1"))
            if result.scalar() != 1:
                health_status["status"] = "unhealthy"
                health_status["errors"].append("Basic connectivity check failed")

            # Get connection pool stats
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

            # Check for blocked queries
            result = session.execute(
                text(
                    """
                SELECT COUNT(*)
                FROM pg_stat_activity
                WHERE wait_event_type = 'Lock'
                AND datname = current_database()
            """
                )
            )
            blocked_queries = result.scalar()
            if blocked_queries > 0:
                health_status["status"] = "degraded"
                health_status["details"]["blocked_queries"] = blocked_queries

            # Check replication status (if applicable)
            try:
                result = session.execute(
                    text(
                        """
                    SELECT state, sync_state
                    FROM pg_stat_replication
                """
                    )
                )
                replication_status = [dict(row) for row in result.mappings()]
                if replication_status:
                    health_status["details"]["replication"] = replication_status
            except Exception:
                pass  # Not a replication setup

            # Check for long-running transactions
            result = session.execute(
                text(
                    """
                SELECT pid, age(clock_timestamp(), query_start) as duration, state, query
                FROM pg_stat_activity
                WHERE state != 'idle'
                AND datname = current_database()
                AND age(clock_timestamp(), query_start) > interval '30 seconds'
            """
                )
            )
            long_running = [dict(row) for row in result.mappings()]
            if long_running:
                health_status["status"] = "degraded"
                health_status["details"]["long_running"] = long_running

            # Check database size
            result = session.execute(
                text(
                    """
                SELECT pg_size_pretty(pg_database_size(current_database()))
            """
                )
            )
            health_status["details"]["size"] = result.scalar()

            # Check connection stats
            result = session.execute(
                text(
                    """
                SELECT state, count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                GROUP BY state
            """
                )
            )
            health_status["details"]["connections"] = dict(result.fetchall())

            # Check for open transactions
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


def init_app(app: Flask) -> None:
    global _initialized
    if _initialized:
        return

    logger.info("Initializing database with init_app(app)")

    # Explicitly create app-bound state instead of using current_app
    if not hasattr(app, "_db_state"):
        app._db_state = {
            "engine": None,
            "Session": None,
            "initialized": False,
            "initializing": True,
        }

    try:
        # Create engine and session factory directly on app's state
        app._db_state["engine"] = create_db_engine(app.config["DATABASE_URI"])
        engine = app._db_state["engine"]

        # Verify connection using raw connection without nested transactions
        with engine.connect() as conn:
            # Execute validation query without transaction management
            result = conn.execute(text("SELECT 1"))
            result.close()  # Explicitly close result
            conn.commit()  # Commit any implicit transaction

        # Create custom session class
        class CustomSession(Session):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault('autocommit', False)
                kwargs.setdefault('autoflush', False)
                super().__init__(*args, **kwargs)

        # Create session factory with explicit transaction control
        session_factory = sessionmaker(
            class_=CustomSession,
            bind=engine,
            autocommit=False,  # Explicit control
            autoflush=False,
            expire_on_commit=False,
            twophase=False,
            info={
                "isolation_level": "READ COMMITTED",
                "autoflush": False
            }
        )
        app._db_state["Session"] = scoped_session(session_factory)
        app._db_state["initialized"] = True
        _initialized = True

        logger.info("Database initialized and verified for app %s", app.name)

    except Exception as e:
        app._db_state["initialized"] = False
        logger.error("Database initialization failed for app %s: %s", app.name, str(e))
        raise
