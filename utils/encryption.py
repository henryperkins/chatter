import base64
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""

    pass


def encrypt_api_key(api_key: str, encryption_key: str) -> str:
    """Encrypt API key using Fernet symmetric encryption."""
    try:
        if not api_key:
            raise EncryptionError("API key is required")
        if not encryption_key:
            raise EncryptionError("Encryption key is required")
            
        # Ensure encryption_key is properly encoded
        try:
            key_bytes = encryption_key.encode()
            # Verify it's valid base64
            base64.urlsafe_b64decode(key_bytes)
        except Exception as e:
            logger.error("Invalid encryption key format")
            raise EncryptionError("Invalid encryption key format") from e
            
        cipher_suite = Fernet(key_bytes)
        encrypted_key = cipher_suite.encrypt(api_key.encode())
        return encrypted_key.decode()
    except EncryptionError:
        raise
    except Exception as e:
        logger.error("Encryption error: %s", str(e))
        raise EncryptionError(f"Failed to encrypt API key: {str(e)}")


def decrypt_api_key(encrypted_key: str, encryption_key: str) -> str:
    """Decrypt API key using Fernet symmetric encryption."""
    try:
        if not encrypted_key:
            raise EncryptionError("Cannot decrypt: Encrypted key is empty")
        if not encryption_key:
            raise EncryptionError("Cannot decrypt: Encryption key is missing")
            
        # Ensure encryption_key is properly encoded
        try:
            key_bytes = encryption_key.encode()
            # Verify it's valid base64
            base64.urlsafe_b64decode(key_bytes)
        except Exception as e:
            logger.error("Invalid encryption key format")
            raise EncryptionError("Invalid encryption key format") from e
            
        cipher_suite = Fernet(key_bytes)
        try:
            decrypted_key = cipher_suite.decrypt(encrypted_key.encode())
            return decrypted_key.decode()
        except InvalidToken as e:
            logger.error("Invalid or corrupted encrypted key")
            raise EncryptionError("Invalid or corrupted encrypted key") from e
    except EncryptionError:
        raise
    except Exception as e:
        logger.error("Decryption error: %s", str(e))
        raise EncryptionError(f"Failed to decrypt API key: {str(e)}")
