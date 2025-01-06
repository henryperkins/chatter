# database.py

import sqlite3
import time
from typing import Optional, Iterator
from flask import g, current_app, Flask
import click
from flask.cli import with_appcontext
from datetime import datetime
from contextlib import contextmanager

def get_db() -> sqlite3.Connection:
    """Open a new database connection if there is none yet for the current application context."""
    if "db" not in g:
        # Register a converter for timestamps
        sqlite3.register_converter(
            "TIMESTAMP", lambda x: datetime.fromisoformat(x.decode())
        )
        g.db = sqlite3.connect(
            current_app.config.get("DATABASE", "chat_app.db"),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,
            timeout=30.0
        )
        g.db.row_factory = sqlite3.Row
        # Enable foreign key constraints for the connection
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

def close_db(e: Optional[BaseException] = None) -> None:
    """Close the database connection if it exists."""
    db = g.pop("db", None)
    if db is not None:
        db.close()

@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """
    Context manager for handling database connections using Flask's application context.
    Automatically commits transactions and handles rollbacks on errors.
    """
    db = get_db()
    try:
        db.execute("BEGIN")
        yield db
        if db.in_transaction:
            db.commit()
    except sqlite3.Error as e:
        if db.in_transaction:
            db.rollback()
        current_app.logger.error(f"Database error: {str(e)}")
        raise
    finally:
        close_db()

def init_db():
    """Initialize the database using the schema.sql file."""
    try:
        with db_connection() as db:
            with current_app.open_resource("schema.sql") as f:
                script = f.read().decode("utf8")
                db.executescript(script)
            current_app.logger.info("Database initialized successfully")
    except Exception as e:
        current_app.logger.error(f"Failed to initialize database: {e}")
        raise

@click.command("init-db")
@with_appcontext
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")

def init_app(app: Flask) -> None:
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
