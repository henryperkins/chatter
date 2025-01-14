# models/base.py

import logging
from contextlib import contextmanager
from sqlalchemy.orm import Session
from database import get_db_session

logger = logging.getLogger(__name__)


@contextmanager
def db_session_scope():
    """
    Provide a transactional scope around a series of operations.
    """
    session_gen = get_db_session()
    session: Session = next(session_gen)
    try:
        yield session
    except Exception as e:
        session.rollback()
        logger.error(f"Session rollback due to exception: {e}")
        raise
    finally:
        session.close()


# Base is imported from database.py
from database import Base

# Now, all ORM models should inherit from Base
