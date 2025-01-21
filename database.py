# database.py

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

# Connection pool settings for PostgreSQL
POOL_SIZE = 5  # Number of connections to keep in the pool
MAX_OVERFLOW = 10  # Maximum number of connections to create beyond the pool size
POOL_RECYCLE = 3600  # Recycle connections after 1 hour (PostgreSQL default is 1 hour)
POOL_TIMEOUT = 30  # Timeout for acquiring a connection from the pool

# Global engine and Session objects
engine = None
Session = None


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Get a database session for PostgreSQL.
    """
    if 'Session' not in globals() or Session is None:
        raise RuntimeError("Database session is not initialized. Call init_app(app) first.")

    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session rollback due to exception: {e}")
        raise
    finally:
        session.close()






def close_db(e: Optional[BaseException] = None) -> None:
    """Clean up the database session."""
    Session.remove()


def init_db() -> None:
    """Initialize database tables."""
    try:
        with db_session() as db:
            with current_app.open_resource("schema.sql") as f:
                # Execute each statement separately to handle SQLAlchemy
                from sqlalchemy import text

                for statement in f.read().decode("utf8").split(";"):
                    if statement.strip():
                        db.execute(text(statement))
                db.commit()
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
    """
    Register database functions with Flask app and initialize PostgreSQL connection.
    """
    global engine, Session

    # Configure PostgreSQL connection
    engine = create_engine(
        app.config["DATABASE_URI"],
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_recycle=POOL_RECYCLE,
        pool_timeout=POOL_TIMEOUT,
    )

    # Create a scoped session for PostgreSQL
    Session = scoped_session(sessionmaker(bind=engine))

    # Register cleanup function
    app.teardown_appcontext(close_db)

    # Add CLI command for database initialization
    app.cli.add_command(init_db_command)
