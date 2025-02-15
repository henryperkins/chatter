"""Base model configuration for SQLAlchemy."""
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, declared_attr

class Base(MappedAsDataclass, DeclarativeBase):
    """Base class for all models with dataclass support."""
    __abstract__ = True
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Default tablename is lowercase class name."""
        return cls.__name__.lower() + 's'
