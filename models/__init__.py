# models/__init__.py
from .base import BaseModel

# First import models that don't have dependencies
from .user import User
from .provider import Provider

# Then import models with dependencies in the correct order
from .model import Model
from .chat import Chat

# Expose all models
__all__ = [
    "BaseModel",
    "User",
    "Provider",
    "Model",
    "Chat"
]

def init_models(engine):
    """Initialize all models and configure their mappers."""
    from sqlalchemy import orm
    BaseModel.metadata.create_all(bind=engine)
    orm.configure_mappers()
