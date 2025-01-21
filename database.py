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

# Global engine and Session objects
engine = None
Session: Optional[ScopedSession[SessionType]] = None
_initialized = False

def is_initialized() -> bool:
    return _initialized and Session is not None
@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Get a database session for PostgreSQL.
    """
    if not current_app:
        raise RuntimeError("Cannot access database outside of Flask application context")

    if not is_initialized():
        raise RuntimeError("Database session is not initialized. Call init_app(app) first.")

    if Session is None:
        raise RuntimeError("Session is not initialized")

    session = Session()  # type: ignore
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
    global Session, _initialized
    if Session is not None:
        if hasattr(Session, 'remove'):
            Session.remove()  # type: ignore
        Session = None
        _initialized = False


def execute_statement(db, statement: str) -> None:
    """Execute a single SQL statement with error handling."""
    try:
        db.execute(text(statement))
        db.commit()
    except Exception as e:
        db.rollback()
        raise e


def init_db() -> None:
    """Initialize database tables."""
    try:
        with db_session() as db:
            with current_app.open_resource("schema.sql") as f:
                sql_content = f.read().decode("utf8")

                # Split scripts by semicolon and filter out empty statements
                statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

                # Execute CREATE TABLE statements first
                for statement in statements:
                    if "CREATE TABLE" in statement.upper():
                        try:
                            db.execute(text(statement))
                            db.commit()
                            logger.info(f"Created table from statement: {statement[:50]}...")
                        except Exception as e:
                            logger.error(f"Error creating table: {e}")
                            raise

                # Then execute CREATE INDEX statements
                for statement in statements:
                    if "CREATE INDEX" in statement.upper():
                        try:
                            db.execute(text(statement))
                            db.commit()
                            logger.info(f"Created index from statement: {statement[:50]}...")
                        except Exception as e:
                            logger.warning(f"Warning creating index: {e}")
                            # Don't raise here, as index creation failures are not fatal

                logger.info("Database initialization completed successfully")

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
    logger.info("Initializing database with init_app(app)")
    if not app.config.get("DATABASE_URI"):
        logger.error("DATABASE_URI is not set in app configuration.")
    logger.info("Database engine and session initialized successfully.")
    logger.info("Database functions registered with Flask app.")
    global engine, Session, _initialized

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
    _initialized = True

    # Register cleanup function
    app.teardown_appcontext(close_db)

    # Add CLI command for database initialization
    app.cli.add_command(init_db_command)
