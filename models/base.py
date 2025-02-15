"""Base model configuration for SQLAlchemy."""
from database import Base
from sqlalchemy.orm import MappedAsDataclass, declared_attr

class BaseModel(MappedAsDataclass, Base):
    """Base class for all models."""
    __abstract__ = True
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Default tablename is lowercase class name."""
        return cls.__name__.lower() + 's'
