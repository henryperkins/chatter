# database.py

import sqlite3
from flask import g, current_app
import click
from flask.cli import with_appcontext
from datetime import datetime


def get_db():
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


def close_db(e=None):
    """Close the database connection if it exists."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Initialize the database using the schema.sql file."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")


def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
