Here's a focused 3-phase plan specifically targeting database interaction safety and ORM alignment:

Phase 1: Eliminate Raw SQL & Atomic Transactions (5 days)

ORM Conversion Protocol (All Model Files)
# models/chat.py BEFORE
def get_user_chats(user_id):
    with db_session() as db:
        result = db.execute(text("""
            SELECT c.id, c.title, COUNT(m.id) 
            FROM chats c LEFT JOIN messages m 
            ON c.id = m.chat_id 
            WHERE c.user_id = :user_id
            GROUP BY c.id
        """), {"user_id": user_id})

# AFTER
from sqlalchemy import func
from models import Chat, Message

def get_user_chats(session, user_id):
    return (session.query(
                Chat.id,
                Chat.title,
                func.count(Message.id).label('message_count')
            )
            .outerjoin(Message)
            .filter(Chat.user_id == user_id)
            .group_by(Chat.id)
            .all())
Transaction Atomicity Framework (database.py)
from contextlib import contextmanager
from sqlalchemy.exc import DatabaseError

@contextmanager
def atomic(session):
    """Guarantee transaction atomicity with retries"""
    try:
        with session.begin_nested():
            yield
        session.commit()
    except DatabaseError as e:
        session.rollback()
        if _should_retry(e):
            raise RetryableError from e
        raise
Phase 2: Session & Connection Safety (4 days)

Strict Session Lifecycle (core/db_session.py)
from sqlalchemy.orm import scoped_session, sessionmaker

Session = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        twophase=True  # For distributed transactions
    )
)

@contextmanager
def safe_session():
    """Enforce session boundaries with cleanup"""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        Session.remove()  # Clear thread-local scope
Connection Pool Enforcement (database.py)
from sqlalchemy.pool import QueuePool
from tenacity import retry, wait_exponential

engine = create_engine(
    config.SQLALCHEMY_DATABASE_URI,
    poolclass=QueuePool,
    pool_size=15,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=3600
)

@retry(wait=wait_exponential(multiplier=1, min=4, max=10))
def get_safe_connection():
    return engine.connect()
Phase 3: Validation & Enforcement (3 days)

ORM Compliance Checks (pre-commit hook)
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: forbid-raw-sql
      name: Block raw SQL
      entry: grep -rn 'text(' --include='*.py'
      language: system
      pass_filenames: false
      always_run: true
Transaction Safety Tests (tests/test_transactions.py)
def test_file_upload_atomicity():
    try:
        with safe_session() as s, atomic(s):
            # Create DB record
            f = UploadedFile(...)
            s.add(f)
            
            # Simulate failed FS operation
            raise OSError("Disk full")
            
    except OSError:
        with safe_session() as s:
            assert not s.query(UploadedFile).filter_by(id=f.id).exists()
            assert not os.path.exists(f.filepath)
Critical File Targets:

models/chat.py (4 raw SQL queries)
models/uploaded_file.py (FS/DB sync)
database.py (connection handling)
models/user.py (3 unsafe queries)
routes/auth_routes.py (session mixing)
Implementation Order:

Create core/db_session.py (Day 1)
Convert models/chat.py (Day 2-3)
Update models/uploaded_file.py (Day 4)
Refactor database.py (Day 5)
Add validation tooling (Day 6-7)
Let me know which component you'd like to implement first, and I'll provide the exact code changes with migration steps.