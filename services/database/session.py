from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, Session
from sqlalchemy.pool import QueuePool
import logging
from typing import Optional, Generator
from flask import g, current_app, Flask
import click
from flask.cli import with_appcontext
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Connection pool settings
POOL_SIZE = 5  # Increased for better concurrency
MAX_OVERFLOW = 10  # Allow more overflow connections
POOL_RECYCLE = 3600  # Recycle connections after 1 hour
POOL_TIMEOUT = 60  # Increased timeout for operations

def get_engine(db_path: Optional[str] = None):
    """Get or create SQLAlchemy engine with connection pool.
    
    Args:
        db_path: Optional database path. If None, uses app config.
        
    Returns:
        SQLAlchemy Engine instance
    """
    if "db_engine" not in g:
        db_path = db_path or str(current_app.config.get("DATABASE", "chat_app.db"))
        g.db_engine = create_engine(
            f"sqlite:///{db_path}",
            poolclass=QueuePool,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_recycle=POOL_RECYCLE,
            pool_timeout=POOL_TIMEOUT,
            connect_args={"timeout": 30},
        )
    return g.db_engine

@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.
    
    This is the primary way to interact with the database. Use as a context manager:
    
    with db_session() as session:
        session.query(...)
    
    The session will automatically handle commit/rollback and proper cleanup.
    
    Yields:
        SQLAlchemy Session object
    
    Raises:
        Exception: Any exception that occurs during database operations
    """
    if "db_session" not in g:
        engine = get_engine()
        g.db_session = scoped_session(sessionmaker(bind=engine))

    session = g.db_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session rollback due to exception: {e}", exc_info=True)
        raise
    finally:
        session.close()

def close_db(e: Optional[BaseException] = None) -> None:
    """Clean up database resources.
    
    This should be registered as a teardown function with the app.
    """
    db_session = g.pop("db_session", None)
    if db_session is not None:
        db_session.remove()
    
    db_engine = g.pop("db_engine", None)
    if db_engine is not None:
        db_engine.dispose()
        logger.debug("Database engine disposed")

def init_db() -> None:
    """Initialize database tables."""
    try:
        with db_session() as session:
            with current_app.open_resource("schema.sql") as f:
                # Execute each statement separately
                from sqlalchemy import text
                for statement in f.read().decode("utf8").split(";"):
                    if statement.strip():
                        session.execute(text(statement))
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise RuntimeError(
            "Failed to initialize the database. Please check the schema file and try again."
        )

@click.command("init-db")
@with_appcontext
def init_db_command():
    """Flask CLI command to initialize database."""
    init_db()
    click.echo("Initialized the database.")

def init_app(app: Flask) -> None:
    """Register database functions with Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)