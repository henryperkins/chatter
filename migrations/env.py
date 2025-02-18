import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Import Flask app and SQLAlchemy instance
from app import create_app, db

# Create Flask app instance
app = create_app()

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# Set target_metadata using the SQLAlchemy instance from Flask-SQLAlchemy
target_metadata = db.Model.metadata

def run_migrations_offline():
    """
    Run migrations in 'offline' mode.
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable here
    as well. By skipping the Engine creation, we don't even need
    a DBAPI to be available.
    """
    url = app.config['SQLALCHEMY_DATABASE_URI']
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """
    Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    with app.app_context():
        connectable = db.engine

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata
            )

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
