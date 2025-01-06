import sqlite3
import logging
from typing import Optional, Iterator
from flask import g, current_app, Flask
from contextlib import contextmanager
import click
from flask.cli import with_appcontext

logger = logging.getLogger(__name__)


def get_db() -> sqlite3.Connection:
    """Get database connection from Flask app context."""
    if "db" not in g:
        db_path = str(current_app.config.get("DATABASE", "chat_app.db"))
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e: Optional[BaseException] = None) -> None:
    """Close database connection."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """Context manager for database operations."""
    connection = None
    try:
        db_path = str(current_app.config.get("DATABASE", "chat_app.db"))
        connection = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN")
        yield connection
        connection.commit()
    except Exception as e:
        if connection:
            connection.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if connection:
            connection.close()


def init_db() -> None:
    """Initialize database tables."""
    try:
        with db_connection() as db:
            with current_app.open_resource("schema.sql") as f:
                db.executescript(f.read().decode("utf8"))
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


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
