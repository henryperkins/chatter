import base64
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""
    pass

def encrypt_api_key(api_key: str, encryption_key: str) -> str:
    """Encrypt an API key."""
    try:
        if not api_key:
            raise ValueError("API key cannot be empty")

        f = Fernet(encryption_key.encode())
        return f.encrypt(api_key.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to encrypt API key: {str(e)}")
        raise EncryptionError(f"Failed to encrypt API key: {str(e)}")

def decrypt_api_key(encrypted_key: str, encryption_key: str) -> str:
    """Decrypt an API key."""
    try:
        if not encrypted_key:
            raise ValueError("Encrypted key cannot be empty")

        f = Fernet(encryption_key.encode())
        return f.decrypt(encrypted_key.encode()).decode()
    except InvalidToken:
        logger.error("Invalid or corrupted encrypted key")
        raise EncryptionError("Invalid or corrupted encrypted key")
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {str(e)}")
        raise EncryptionError(f"Failed to decrypt API key: {str(e)}")
