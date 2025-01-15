import bcrypt
import os
from typing import Optional

def hash_password(password: str) -> bytes:
    """Hash a password using bcrypt."""
    cost_factor = int(os.environ.get("BCRYPT_COST_FACTOR", 12))
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=cost_factor)
    )

def check_password(password: str, hashed_pw: bytes) -> bool:
    """Check a password against its hashed value."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_pw)
