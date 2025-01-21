import logging
# Removed unused imports
from sqlalchemy.ext.declarative import declarative_base


logger = logging.getLogger(__name__)


# Removed redundant db_session function; using db_session from database.py instead


# Import Base from SQLAlchemy
Base = declarative_base()

def row_to_dict(row, fields=None):
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
