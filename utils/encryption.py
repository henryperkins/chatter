import base64
import logging
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from config import Config

logger = logging.getLogger(__name__)

class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""
    pass

def validate_encryption_key(key: str) -> bytes:
    """Validate and format encryption key."""
    try:
        # Try to decode as base64 first
        try:
            decoded = base64.b64decode(key, validate=True)
            if len(decoded) == 32:
                return key.encode()
        except Exception:
            pass

        # If not valid base64 or not 32 bytes, hash it
        key_bytes = hashlib.sha256(key.encode()).digest()
        return base64.b64encode(key_bytes)
    except Exception as e:
        raise EncryptionError(f"Invalid encryption key format: {str(e)}")

def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key."""
    try:
        if not api_key:
            raise ValueError("API key cannot be empty")

        key = validate_encryption_key(Config.ENCRYPTION_KEY)
        f = Fernet(key)
        return f.encrypt(api_key.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to encrypt API key: {str(e)}")
        raise EncryptionError(f"Failed to encrypt API key: {str(e)}")

def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key."""
    try:
        if not encrypted_key:
            raise ValueError("Encrypted key cannot be empty")

        key = validate_encryption_key(Config.ENCRYPTION_KEY)
        f = Fernet(key)
        return f.decrypt(encrypted_key.encode()).decode()
    except InvalidToken:
        logger.error("Invalid or corrupted encrypted key")
        raise EncryptionError("Invalid or corrupted encrypted key")
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {str(e)}")
        raise EncryptionError(f"Failed to decrypt API key: {str(e)}")
