import logging
# Removed unused imports
from sqlalchemy.ext.declarative import declarative_base


logger = logging.getLogger(__name__)


# Removed redundant db_session function; using db_session from database.py instead


# Import Base from SQLAlchemy
Base = declarative_base()

def row_to_dict(row):
    """Convert a SQLAlchemy row object to a dictionary."""
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
