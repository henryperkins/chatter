 # database.py

import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import scoped_session, sessionmaker, Session as SessionType
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
    """Get a database session with proper transaction handling and retries"""
    if not current_app:
        raise RuntimeError("Cannot access database outside of Flask application context")

    db_state = get_db_state()
    if db_state['Session'] is None:
        raise RuntimeError("Session factory is not initialized")

    session = db_state['Session']()
    try:
        # Add advisory lock to prevent concurrent modifications
        session.execute(text("SET lock_timeout = '5s'"))
        
        yield session
        
        # Only commit if no errors and session is active
        if session.is_active and not session.in_transaction():
            try:
                session.commit()
            except Exception as commit_error:
                logger.error(f"Commit failed: {commit_error}")
                if session.is_active:
                    session.rollback()
                raise
    except OperationalError as e:
        session.rollback()
        logger.error(f"Database operation failed: {str(e)}")
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error in database operation: {str(e)}")
        raise
    finally:
        try:
            if session.is_active:
                session.close()
        except Exception as e:
            logger.warning(f"Error closing session: {str(e)}")
        finally:
            # Ensure session is removed from registry
            if 'Session' in db_state and hasattr(db_state['Session'], 'remove'):
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
        engine = create_db_engine(db_uri)
        
        # Configure session factory with proper isolation
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
        
        # Add connection health check
        @event.listens_for(engine, "engine_connect")
        def ping_connection(connection, branch):
            if branch:
                return
                
            # Run a simple query to check connection
            try:
                connection.scalar(text("SELECT 1"))
            except Exception:
                connection.invalidate()
                raise

        # Drop all existing tables
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.commit()

        # Set up database state
        db_state = get_db_state()
        db_state['engine'] = engine
        db_state['Session'] = scoped_session(
            sessionmaker(bind=engine),
            scopefunc=lambda: id(g) if hasattr(g, '_get_current_object') else None
        )

        # Read and execute schema.sql
        with current_app.open_resource('schema.sql') as f:
            schema_sql = f.read().decode('utf8')
            with engine.connect() as conn:
                # Execute schema as a single transaction
                conn.execute(text(schema_sql))
                conn.commit()

        # Create default provider and model
        with db_session() as db:
            # Create default provider if it doesn't exist
            provider_exists = db.execute(text(
                "SELECT id FROM providers WHERE slug = 'azure-openai'"
            )).scalar()
            
            if not provider_exists:
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
                    "api_base_url": os.getenv("AZURE_API_ENDPOINT", "").rstrip("/"),
                    "capabilities": json.dumps({
                        "supports_streaming": True,
                        "max_tokens": 4000
                    }),
                    "api_version": os.getenv("AZURE_API_VERSION", "2023-05-15")
                }).scalar()
            else:
                provider_id = provider_exists

            # Create default model if it doesn't exist
            default_model = db.execute(text(
                "SELECT id FROM models WHERE is_default = TRUE"
            )).scalar()
            
            if not default_model:
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
                    "api_endpoint": os.getenv("AZURE_API_ENDPOINT", "https://hp-east2.openai.azure.com/openai/deployments/gpt-deployment?api-version=2024-12-01-preview"),
                    "api_key": os.getenv("AZURE_API_KEY"),
                    "model_type": "azure",
                    "temperature": float(os.getenv("DEFAULT_TEMPERATURE", "0.7")),
                    "max_tokens": int(os.getenv("DEFAULT_MAX_TOKENS", "4000")),
                    "max_completion_tokens": int(os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "4000")),
                    "requires_o1_handling": True,
                    "supports_streaming": True,
                    "api_version": os.getenv("AZURE_API_VERSION", "2023-05-15")
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
            # Configure PostgreSQL connection
            connect_args = {}
            db_state['engine'] = create_engine(
                app.config["DATABASE_URI"],
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_recycle=POOL_RECYCLE,
                pool_timeout=POOL_TIMEOUT,
                pool_pre_ping=POOL_PRE_PING,  # Add connection health checks
                connect_args=connect_args
            )

            # Create a scoped session factory bound to the application context
            # Configure session with proper isolation level and expiration
            db_state['Session'] = scoped_session(
                sessionmaker(
                    bind=db_state['engine'],
                    autocommit=False,
                    autoflush=False,
                    expire_on_commit=True
                ),
                scopefunc=lambda: id(g) if hasattr(g, '_get_current_object') else None
            )

            logger.info("Database engine and session initialized successfully")

            # Initialize database schema only
            init_db(app.config["DATABASE_URI"])

            # Register cleanup function
            app.teardown_appcontext(close_db)

            # Add CLI command for database initialization
            app.cli.add_command(init_db_command)
            
            logger.info("Database functions registered with Flask app")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}", exc_info=True)
            raise
