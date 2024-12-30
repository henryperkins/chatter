import sqlite3
from flask import g

DATABASE = "chat_app.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql", mode="r") as f:
            db.cursor().executescript(f.read())
        db.commit()


def add_model(name, description, model_type='azure', api_endpoint=None, api_key=None, temperature=1.0, max_tokens=32000, is_default=False):
    """Add a new model to the database."""
    db = get_db()
    db.execute(
        "INSERT INTO models (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default),
    )
    db.commit()


def get_models():
    """Retrieve all models from the database."""
    db = get_db()
    return db.execute(
        "SELECT id, name, description, model_type, api_endpoint, temperature, max_tokens, is_default FROM models"
    ).fetchall()

def get_default_model():
    """Retrieve the default model configuration."""
    db = get_db()
    model = db.execute(
        "SELECT * FROM models WHERE is_default = 1 LIMIT 1"
    ).fetchone()
    if not model:
        model = db.execute(
            "SELECT * FROM models ORDER BY id LIMIT 1"
        ).fetchone()
    return model


def update_model(model_id, name, description, model_type=None, api_endpoint=None, api_key=None, temperature=None, max_tokens=None, is_default=None):
    """Update an existing model in the database."""
    db = get_db()
    db.execute(
        "UPDATE models SET name = ?, description = ?, model_type = ?, api_endpoint = ?, api_key = ?, temperature = ?, max_tokens = ?, is_default = ? WHERE id = ?",
        (name, description, model_type, api_endpoint, api_key, temperature, max_tokens, is_default, model_id),
    )
    db.commit()


def delete_model(model_id):
    """Delete a model from the database."""
    db = get_db()
    db.execute("DELETE FROM models WHERE id = ?", (model_id,))
    db.commit()
