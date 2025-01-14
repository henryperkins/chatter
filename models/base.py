import logging
from contextlib import contextmanager
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool
from database import get_db_session, get_db_pool
from sqlalchemy.ext.declarative import declarative_base


logger = logging.getLogger(__name__)


@contextmanager
def db_session(pool: Optional[QueuePool] = None) -> Session:
    """Provide a transactional scope around a series of operations."""
    if pool is None:
        pool = get_db_pool()
    
    session_gen = get_db_session()
    session = next(session_gen)
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session rollback due to exception: {e}")
        raise
    finally:
        session.close()


# Import Base from SQLAlchemy
Base = declarative_base()

def row_to_dict(row):
    """Convert a SQLAlchemy row object to a dictionary."""
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
