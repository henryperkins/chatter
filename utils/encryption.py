import base64
import logging
from cryptography.fernet import Fernet
from config import Config

logger = logging.getLogger(__name__)

class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""
    pass

def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key."""
    try:
        f = Fernet(Config.ENCRYPTION_KEY.encode())
        return f.encrypt(api_key.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to encrypt API key: {str(e)}")
        raise EncryptionError(f"Failed to encrypt API key: {str(e)}")

def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key."""
    try:
        f = Fernet(Config.ENCRYPTION_KEY.encode())
        return f.decrypt(encrypted_key.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {str(e)}")
        return ""  # Return empty string on failure instead of raising
