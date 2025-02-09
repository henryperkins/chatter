import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""

    pass


def encrypt_api_key(api_key: str, encryption_key: str) -> str:
    """Encrypt API key using Fernet symmetric encryption."""
    try:
        if not api_key or not encryption_key:
            raise EncryptionError("API key and encryption key are required")
        cipher_suite = Fernet(encryption_key.encode())
        encrypted_key = cipher_suite.encrypt(api_key.encode())
        return encrypted_key.decode()
    except Exception as e:
        logger.error(f"Encryption error: {str(e)}")
        raise EncryptionError(f"Failed to encrypt API key: {str(e)}")


def decrypt_api_key(encrypted_key: str, encryption_key: str) -> str:
    """Decrypt API key using Fernet symmetric encryption."""
    try:
        if not encrypted_key or not encryption_key:
            raise EncryptionError("Encrypted key and encryption key are required")
        cipher_suite = Fernet(encryption_key.encode())
        decrypted_key = cipher_suite.decrypt(encrypted_key.encode())
        return decrypted_key.decode()
    except Exception as e:
        logger.error(f"Decryption error: {str(e)}")
        raise EncryptionError(f"Failed to decrypt API key: {str(e)}")
