# database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool
import logging
from typing import Optional
from flask import g, current_app, Flask
import click
from flask.cli import with_appcontext

logger = logging.getLogger(__name__)

# Connection pool settings
# Pool settings for SQLite
POOL_SIZE = 5  # Increased for better concurrency
MAX_OVERFLOW = 10  # Allow more overflow connections
POOL_RECYCLE = 3600  # Recycle connections after 1 hour
POOL_TIMEOUT = 60  # Increased timeout for operations

def get_db():
    """Get database connection from Flask app context using connection pool."""
    if "db" not in g:
        db_path = str(current_app.config.get("DATABASE", "chat_app.db"))
        logger.debug(f"Getting database connection from pool to {db_path}")
        
        # Create engine with connection pooling if it doesn't exist
        if "db_engine" not in g:
            g.db_engine = create_engine(
                f"sqlite:///{db_path}",
                poolclass=QueuePool,
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_recycle=POOL_RECYCLE,
                pool_timeout=POOL_TIMEOUT,
                connect_args={
                    "timeout": 30  # SQLite busy timeout in seconds
                }
            )
            g.db_session = scoped_session(sessionmaker(bind=g.db_engine))
        
        g.db = g.db_session()
    return g.db


def close_db(e: Optional[BaseException] = None) -> None:
    """Return database connection to pool."""
    db = g.pop("db", None)
    if db is not None:
        logger.debug("Returning database connection to pool")
        db.close()
    
    # Clean up engine and session at app teardown
    db_engine = g.pop("db_engine", None)
    db_session = g.pop("db_session", None)
    if db_session is not None:
        db_session.remove()
    if db_engine is not None:
        db_engine.dispose()


def init_db() -> None:
    """Initialize database tables."""
    try:
        db = get_db()
        with current_app.open_resource("schema.sql") as f:
            # Execute each statement separately to handle SQLAlchemy
            from sqlalchemy import text
            for statement in f.read().decode("utf8").split(';'):
                if statement.strip():
                    db.execute(text(statement))
            db.commit()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise RuntimeError("Failed to initialize the database. Please check the schema file and try again.")


@click.command("init-db")
@with_appcontext
def init_db_command() -> None:
    """Flask CLI command to initialize database."""
    init_db()
    click.echo("Initialized the database.")


def init_app(app: Flask) -> None:
    """Register database functions with Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
