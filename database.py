 # database.py

from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker, Session as SessionType
from sqlalchemy.orm.session import Session
from sqlalchemy.orm.scoping import scoped_session as ScopedSession
import logging
from typing import Optional, Generator
from flask import g, current_app, Flask
import click
from flask.cli import with_appcontext
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Connection pool settings for PostgreSQL
POOL_SIZE = 5  # Number of connections to keep in the pool
MAX_OVERFLOW = 10  # Maximum number of connections to create beyond the pool size
POOL_RECYCLE = 3600  # Recycle connections after 1 hour (PostgreSQL default is 1 hour)
POOL_TIMEOUT = 30  # Timeout for acquiring a connection from the pool

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
    """Get a database session for PostgreSQL."""
    if not current_app:
        raise RuntimeError("Cannot access database outside of Flask application context")

    if not is_initialized():
        raise RuntimeError("Database not initialized. Make sure init_app() is called during application setup")

    db_state = get_db_state()
    if db_state['Session'] is None:
        raise RuntimeError("Session factory is not initialized")

    session = db_state['Session']()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session rollback due to exception: {e}", exc_info=True)
        raise
    finally:
        if db_state['Session'] is not None:
            db_state['Session'].remove()


def close_db(e: Optional[BaseException] = None) -> None:
    """Clean up the database session."""
    if current_app:
        db_state = get_db_state()
        if db_state['Session'] is not None:
            if hasattr(db_state['Session'], 'remove'):
                db_state['Session'].remove()


def execute_statement(db, statement: str) -> None:
    """Execute a single SQL statement with error handling."""
    try:
        db.execute(text(statement))
        db.commit()
    except Exception as e:
        db.rollback()
        raise e


def init_db(db_uri: str = None) -> None:
    """Initialize database tables."""
    if not current_app:
        raise RuntimeError("Cannot initialize database outside of Flask application context")
        
    db_uri = db_uri or current_app.config["DATABASE_URI"]
    if not db_uri:
        raise ValueError("DATABASE_URI must be provided either directly or in app config")
    
    try:
        # Import all models to ensure they're registered with the metadata
        from models.user import User
        from models.chat import Chat
        from models.model import Model
        from models.provider import Provider
        from models.uploaded_file import UploadedFile
        from models.base import Base
        
        # Create engine with proper PostgreSQL settings
        engine = create_engine(
            db_uri,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_recycle=POOL_RECYCLE,
            pool_timeout=POOL_TIMEOUT
        )
        
        # Drop and recreate all tables
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        # Create a session to create the default model
        Session = sessionmaker(bind=engine)
        with Session() as session:
            create_default_model(session)
        
        logger.info("Database initialization completed successfully with default model")
        
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
    
    # Create default provider first
    default_provider = {
        "name": "Azure OpenAI",
        "slug": "azure-openai",
        "api_base_url": Config.AZURE_API_ENDPOINT,
        "capabilities": {
            "supports_streaming": Config.DEFAULT_SUPPORTS_STREAMING,
            "max_tokens": Config.DEFAULT_MAX_TOKENS
        },
        "requires_authentication": True,
        "api_version_format": Config.AZURE_API_VERSION,
        "created_at": None  # Let the database handle this
    }
    
    try:
        provider_id = Provider.create(default_provider)
        if not provider_id:
            raise ValueError("Failed to create default provider")
            
        # Now create the default model with the provider_id
        default_model = {
            "name": Config.DEFAULT_MODEL_NAME,
            "deployment_name": Config.DEFAULT_DEPLOYMENT_NAME,
            "description": Config.DEFAULT_MODEL_DESCRIPTION,
            "model_type": "gpt",  # Default type
            "provider_id": provider_id,  # Link to the provider we just created
            "api_endpoint": Config.DEFAULT_API_ENDPOINT,
            "api_key": Config.AZURE_API_KEY,
            "temperature": Config.DEFAULT_TEMPERATURE,
            "max_tokens": Config.DEFAULT_MAX_TOKENS,
            "max_completion_tokens": Config.DEFAULT_MAX_COMPLETION_TOKENS,
            "is_default": True,
            "requires_o1_handling": Config.DEFAULT_REQUIRES_O1_HANDLING,
            "supports_streaming": Config.DEFAULT_SUPPORTS_STREAMING,
            "api_version": Config.DEFAULT_API_VERSION,
            "version": 1,
        }
        
        Model.create(default_model)
        logger.info("Default provider and model created successfully")
    except Exception as e:
        logger.error(f"Failed to create default provider and model: {e}", exc_info=True)
        raise

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
            db_state['engine'] = create_engine(
                app.config["DATABASE_URI"],
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_recycle=POOL_RECYCLE,
                pool_timeout=POOL_TIMEOUT,
            )

            # Create a scoped session factory bound to the application context
            db_state['Session'] = scoped_session(
                sessionmaker(bind=db_state['engine']),
                scopefunc=lambda: id(g) if hasattr(g, '_get_current_object') else None
            )

            logger.info("Database engine and session initialized successfully")

            # Create default model if it doesn't exist
            with db_session() as db:
                create_default_model(db)

            # Register cleanup function
            app.teardown_appcontext(close_db)

            # Add CLI command for database initialization
            app.cli.add_command(init_db_command)
            
            logger.info("Database functions registered with Flask app")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}", exc_info=True)
            raise
