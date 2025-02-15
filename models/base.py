"""Base model configuration for SQLAlchemy."""
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, declared_attr

class Base(MappedAsDataclass, DeclarativeBase):
    """Base class for all models with dataclass support."""
    __abstract__ = True
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Default tablename is lowercase class name."""
        return cls.__name__.lower() + 's'

    def __repr__(self):
        return f"<{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in self.__dict__.items() if not k.startswith('_'))})>"
