import logging
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

# Import Base from SQLAlchemy
Base = declarative_base()

def row_to_dict(row):
    """Convert a SQLAlchemy row object to a dictionary."""
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}