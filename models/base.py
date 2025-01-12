import logging
from contextlib import contextmanager
from typing import Dict, List, Any

from database import get_db
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@contextmanager
def db_session():
    """Context manager for handling database sessions."""
    db: Session = get_db()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Database operation failed: {e}")
        raise
    finally:
        db.close()


def row_to_dict(row, fields: List[str]) -> Dict[str, Any]:
    """Convert a SQLAlchemy row to a dictionary."""
    return {field: row._mapping[field] for field in fields}
