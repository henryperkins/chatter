from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from .base import Base

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    success = Column(Boolean, default=False, nullable=False)
    attempted_at = Column(DateTime, default=datetime.utcnow, nullable=False)