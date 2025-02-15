"""Base model configuration for SQLAlchemy."""
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, declared_attr
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class Base(MappedAsDataclass, DeclarativeBase):
    """Base class for all models."""
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Default tablename is lowercase class name."""
        return cls.__name__.lower() + 's'

def row_to_dict(row: Any, fields: Optional[list[str]] = None) -> Dict[str, Any]:
    """Convert a SQLAlchemy row object to a dictionary.
    
    Args:
        row: The SQLAlchemy row object
        fields: Optional list of fields to include. If None, includes all fields.
    
    Returns:
        dict: Dictionary containing the row data
    """
    if fields is None:
        # If no fields specified, get all columns
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
    
    # If fields specified, only include those that exist
    return {field: getattr(row, field) for field in fields if hasattr(row, field)}
