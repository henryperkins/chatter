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
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e: Optional[BaseException] = None) -> None:
    """Close the database connection if it exists."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


class DatabaseConnectionManager:
    """Manages database connections with retry logic and state tracking"""

    def __init__(self) -> None:
        self.connection: Optional[sqlite3.Connection] = None
        self.retry_count: int = 3
        self.retry_delay: float = 1.0

    def create_connection(self) -> sqlite3.Connection:
        """Create a new database connection"""
        return sqlite3.connect(
            current_app.config.get("DATABASE", "chat_app.db"),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,
            timeout=30.0
        )

    def get_connection(self) -> sqlite3.Connection:
        """Get a working database connection with retry logic"""
        for attempt in range(self.retry_count):
            try:
                if self.connection is None:
                    self.connection = self.create_connection()
                    self.connection.row_factory = sqlite3.Row

                # Test connection
                self.connection.execute("SELECT 1").fetchone()
                return self.connection

            except sqlite3.Error:
                if attempt == self.retry_count - 1:
                    raise
                if self.connection:
                    try:
                        self.connection.close()
                    except sqlite3.Error:
                        pass
                    self.connection = None
                time.sleep(self.retry_delay)
        raise sqlite3.Error("Failed to establish database connection")

    def close(self) -> None:
        """Close the connection if it exists"""
        if self.connection:
            try:
                self.connection.close()
            except sqlite3.Error:
                pass
            self.connection = None

@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """
    Context manager for handling database connections with retry logic.
    Automatically commits transactions and handles rollbacks on errors.
    """
    manager = DatabaseConnectionManager()
    connection = None
    try:
        connection = manager.get_connection()
        connection.execute("BEGIN")

        yield connection

        if connection.in_transaction:
            connection.commit()

    except sqlite3.Error as e:
        if connection and connection.in_transaction:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        current_app.logger.error(f"Database error: {str(e)}")
        raise
    finally:
        if connection:
            manager.close()


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
