# models/__init__.py
from .base import Base

# First import models that don't have dependencies
from .user import User
from .provider import Provider

# Then import models with dependencies in the correct order
# Import and expose Model first since Chat depends on it
from .model import Model
from .chat import Chat

# Expose all models
__all__ = [
    "Base",
    "User",
    "Provider",
    "Model",
    "Chat"
]

# After all models are imported, configure mappers
def init_models():
    """Initialize all models and configure their mappers."""
    from sqlalchemy import orm
    Base.metadata.create_all()  # This will create tables if they don't exist
    orm.configure_mappers()

# Call init_models when this module is imported
init_models()