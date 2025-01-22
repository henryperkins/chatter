 # database.py

import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import scoped_session, sessionmaker, Session as SessionType, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import logging
import json
from typing import Optional, Generator
from flask import g, current_app, Flask
import click
from flask.cli import with_appcontext
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Connection pool settings for PostgreSQL
POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT = 30
POOL_PRE_PING = True
# Removed POOL_RECYCLE since it wasn't used consistently

def create_db_engine(db_uri: str):
    return create_engine(
        db_uri,
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_pre_ping=True,
        connect_args={
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5
        }
    )

# Add this line to define SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False)

def with_db_retries(max_attempts=3, wait_seconds=0.5):
    def decorator(func):
        @retry(stop=stop_after_attempt(max_attempts), 
              wait=wait_fixed(wait_seconds),
              retry=retry_if_exception_type(OperationalError))
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except OperationalError as e:
                logger.warning(f"Database operation failed, retrying: {str(e)}")
                raise
        return wrapper
    return decorator

def get_db_state():
    """Get database state from application context"""
    if not hasattr(current_app, 'db_state'):
        current_app.db_state = {
            'engine': None,
            'Session': None,
            'initialized': False
        }
    return current_app.db_state

def is_initialized() -> bool:
    """Check if database is properly initialized."""
    if not current_app:
        return False
    db_state = get_db_state()
    return (db_state['Session'] is not None and 
            db_state['engine'] is not None and
            hasattr(db_state['Session'], 'remove'))
@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Get a database session with proper transaction handling"""
    if not current_app:
        raise RuntimeError("Cannot access database outside of Flask application context")

    db_state = get_db_state()
    if db_state['Session'] is None:
        raise RuntimeError("Session factory is not initialized")

    session = None
    try:
        session = db_state['Session']()
        # Start transaction explicitly
        session.begin()
        
        # Set session parameters
        session.execute(text("SET lock_timeout = '5s'"))
        session.execute(text("SET statement_timeout = '30s'"))
        
        yield session
        
        # Commit if no exception occurred
        session.commit()
    except Exception as e:
        if session and session.in_transaction():
            session.rollback()
        logger.error(f"Database operation failed: {str(e)}")
        raise
    finally:
        if session:
            session.close()
            if hasattr(db_state['Session'], 'remove'):
                db_state['Session'].remove()


def close_db(e: Optional[BaseException] = None) -> None:
    """Clean up the database session."""
    logger.debug("Closing database session")
    if current_app:
        db_state = get_db_state()
        session_factory = db_state.get('Session')
        if session_factory and hasattr(session_factory, 'remove'):
            try:
                # Get the actual session instance
                session = session_factory()
                # Only remove if session is not in a transaction
                if not session.in_transaction():
                    session_factory.remove()
                    logger.debug("Database session closed successfully")
                else:
                    logger.debug("Skipping session removal - transaction in progress")
            except Exception as e:
                logger.error(f"Error closing database session: {str(e)}", exc_info=True)


def execute_statement(db, statement: str) -> None:
    """Execute a single SQL statement with error handling."""
    try:
        db.execute(text(statement))
        db.commit()
    except Exception as e:
        db.rollback()
        raise e


def init_db(db_uri: str = None) -> None:
    """Initialize database with proper connection handling"""
    if not current_app:
        raise RuntimeError("Cannot initialize database outside of Flask application context")
        
    db_uri = db_uri or current_app.config["DATABASE_URI"]
    if not db_uri:
        raise ValueError("DATABASE_URI must be provided either directly or in app config")
    
    try:
        # Create fresh engine
        engine = create_db_engine(db_uri)
        
        # Drop and recreate schema
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.commit()

        # Configure session factory
        global SessionLocal
        SessionLocal = scoped_session(
            sessionmaker(
                bind=engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=True
            ),
            scopefunc=lambda: id(g) if hasattr(g, '_get_current_object') else None
        )
        
        # Set up database state
        db_state = get_db_state()
        db_state['engine'] = engine
        db_state['Session'] = SessionLocal
        
        # Add connection health check
        @event.listens_for(engine, "engine_connect")
        def ping_connection(connection, branch):
            if branch:
                return
            try:
                connection.scalar(text("SELECT 1"))
            except Exception:
                connection.invalidate()
                raise

        # Execute schema.sql
        with current_app.open_resource('schema.sql') as f:
            schema_sql = f.read().decode('utf8')
            with engine.connect() as conn:
                conn.execute(text(schema_sql))
                conn.commit()

        # Create default provider
        with db_session() as db:
            # Create provider without requiring Azure credentials
            provider_id = db.execute(text("""
                INSERT INTO providers (
                    name, slug, api_base_url, capabilities, 
                    requires_authentication, api_version_format
                ) VALUES (
                    'Azure OpenAI', 'azure-openai', :api_base_url,
                    :capabilities, TRUE, :api_version
                )
                RETURNING id
            """), {
                "api_base_url": os.getenv("AZURE_API_ENDPOINT", "https://your-resource.openai.azure.com").rstrip("/"),
                "capabilities": json.dumps({
                    "supports_streaming": True,
                    "max_tokens": 16384,
                    "api_version": "2024-12-01-preview"
                }),
                "api_version": "2024-12-01-preview"
            }).scalar()

            # Create placeholder model with dummy values if env vars not set
            api_endpoint = os.getenv("AZURE_API_ENDPOINT", "https://your-resource.openai.azure.com")
            api_key = os.getenv("AZURE_API_KEY", "dummy-key-please-configure")
            
            if not api_endpoint.startswith("https://") or api_key == "dummy-key-please-configure":
                logger.warning("Using placeholder Azure credentials - please configure AZURE_API_ENDPOINT and AZURE_API_KEY")

            # Create default model with available or placeholder values
            db.execute(text("""
                INSERT INTO models (
                    provider_id, name, deployment_name, description,
                    api_endpoint, api_key, model_type, temperature,
                    max_tokens, max_completion_tokens, requires_o1_handling,
                    supports_streaming, is_default, api_version, version
                ) VALUES (
                    :provider_id, :name, :deployment_name, :description,
                    :api_endpoint, :api_key, :model_type, :temperature,
                    :max_tokens, :max_completion_tokens, :requires_o1_handling,
                    :supports_streaming, TRUE, :api_version, 1
                )
            """), {
                "provider_id": provider_id,
                "name": os.getenv("DEFAULT_MODEL_NAME", "GPT-4"),
                "deployment_name": os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-deployment"),
                "description": os.getenv("DEFAULT_MODEL_DESCRIPTION", "Azure GPT-4 Model"),
                "api_endpoint": api_endpoint,
                "api_key": api_key,
                "model_type": "azure",
                "temperature": float(os.getenv("DEFAULT_TEMPERATURE", "0.7")),
                "max_tokens": int(os.getenv("DEFAULT_MAX_TOKENS", "16384")),
                "max_completion_tokens": int(os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "16384")),
                "requires_o1_handling": True,
                "supports_streaming": True,
                "api_version": "2024-12-01-preview"
            })
            db.commit()
            logger.info("Default model configuration created successfully")
        
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise RuntimeError(
            "Failed to initialize the database. Please check the database connection and try again."
        )


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Flask CLI command to initialize database."""
    init_db()
    click.echo("Initialized the database.")


def create_default_model(db) -> None:
    """Create default provider and model if they don't exist"""
    from models import Model, Provider
    from config import Config
    
    # Check if default model exists
    default_exists = db.execute(text("SELECT COUNT(*) FROM models WHERE is_default = TRUE")).scalar()
    if default_exists:
        return

    logger.info("Creating default provider and model")
    
    # Try to get existing provider first
    provider_id = db.execute(text(
        "SELECT id FROM providers WHERE name = :name OR slug = :slug"
    ), {
        "name": "Azure OpenAI",
        "slug": "azure-openai"
    }).scalar()
    
    if not provider_id:
        try:
            # Create default provider if it doesn't exist
            default_provider = {
                "name": "Azure OpenAI",
                "slug": "azure-openai",
                "api_base_url": Config.AZURE_API_ENDPOINT.rstrip("/"),
                "capabilities": {
                    "supports_streaming": Config.DEFAULT_SUPPORTS_STREAMING,
                    "max_tokens": Config.DEFAULT_MAX_TOKENS
                },
                "requires_authentication": True,
                "api_version_format": Config.DEFAULT_API_VERSION
            }
            
            try:
                provider_id = Provider.create(default_provider)
                if not provider_id:
                    raise ValueError("Failed to create default provider")
            except ValueError as e:
                if "already exists" not in str(e):
                    raise
                # If provider exists, get its ID
                provider_id = db.execute(text(
                    "SELECT id FROM providers WHERE name = :name OR slug = :slug"
                ), {
                    "name": default_provider["name"],
                    "slug": default_provider["slug"]
                }).scalar()
                
            # Now create the default model with the provider_id
            default_model = {
                "name": Config.DEFAULT_MODEL_NAME,
                "deployment_name": Config.DEFAULT_DEPLOYMENT_NAME,
                "description": Config.DEFAULT_MODEL_DESCRIPTION,
                "provider_id": provider_id,  # Link to the provider we just created
                "api_endpoint": Config.DEFAULT_API_ENDPOINT,
                "api_key": Config.AZURE_API_KEY,
                "model_type": "gpt",
                "temperature": Config.DEFAULT_TEMPERATURE,
                "max_tokens": Config.DEFAULT_MAX_TOKENS,
                "max_completion_tokens": Config.DEFAULT_MAX_COMPLETION_TOKENS,
                "is_default": True,
                "requires_o1_handling": Config.DEFAULT_REQUIRES_O1_HANDLING,
                "supports_streaming": Config.DEFAULT_SUPPORTS_STREAMING,
                "api_version": Config.DEFAULT_API_VERSION,
                "version": 1
            }
            
            Model.create(default_model)
            logger.info("Default provider and model created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create default provider and model: {e}", exc_info=True)
            raise

def monitor_connections():
    """Monitor and log connection pool status"""
    with db_session() as session:
        stats = session.execute(text("""
            SELECT 
                state, count(*) 
            FROM pg_stat_activity 
            WHERE datname = current_database()
            GROUP BY state
        """)).fetchall()
        
        logger.info(f"Database connection stats: {dict(stats)}")
        
        pool_stats = {
            'checked_out': session.connection().connection.pool.checkedout(),
            'checked_in': session.connection().connection.pool.checkedin(),
            'overflow': session.connection().connection.pool.overflow()
        }
        logger.info(f"Connection pool stats: {pool_stats}")

def init_app(app: Flask) -> None:
    """Register database functions with Flask app and initialize PostgreSQL connection."""
    logger.info("Initializing database with init_app(app)")
    
    if not app.config.get("DATABASE_URI"):
        logger.error("DATABASE_URI is not set in app configuration.")
        raise ValueError("DATABASE_URI must be set in app configuration")
        
    db_state = get_db_state()

    # Only initialize if not already initialized
    if not is_initialized():
        try:
            # Configure PostgreSQL connection with explicit transaction control
            db_state['engine'] = create_engine(
                app.config["DATABASE_URI"],
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_timeout=POOL_TIMEOUT,
                pool_pre_ping=True,
                isolation_level='READ COMMITTED',
                execution_options={
                    "isolation_level": "READ COMMITTED",
                    "autocommit": False
                }
            )

            # Create a scoped session factory with explicit transaction settings
            db_state['Session'] = scoped_session(
                sessionmaker(
                    bind=db_state['engine'],
                    autocommit=False,
                    autoflush=False,
                    expire_on_commit=False,
                    twophase=False  # Disable two-phase commit
                )
            )

            # Initialize database schema
            init_db(app.config["DATABASE_URI"])

            # Register cleanup function
            app.teardown_appcontext(close_db)

            logger.info("Database initialization completed successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}", exc_info=True)
            raise
