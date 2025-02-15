import base64
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""

    pass


def encrypt_api_key(api_key: str, encryption_key: str) -> str:
    """Encrypt API key using Fernet symmetric encryption."""
    import os
    if os.environ.get('FLASK_ENV') == 'development':
        logger.debug("Development environment detected, skipping encryption")
        return api_key
    try:
        if not api_key:
            raise EncryptionError("API key is required")
        if not encryption_key:
            raise EncryptionError("Encryption key is required")

        logger.debug("Starting encryption with key length: %d", len(encryption_key))

        # Normalize encryption key
        key_bytes = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
        
        # Ensure it's 32 bytes for Fernet
        decoded_key = base64.urlsafe_b64decode(key_bytes)
        if len(decoded_key) != 32:
            logger.error("Invalid key length after decoding: %d bytes", len(decoded_key))
            raise EncryptionError("Encryption key must decode to 32 bytes")
            
        # Create Fernet instance with validated key
        cipher_suite = Fernet(key_bytes)
        
        # Ensure consistent API key encoding
        api_bytes = api_key.encode() if isinstance(api_key, str) else api_key
        
        # Encrypt with Fernet
        encrypted_bytes = cipher_suite.encrypt(api_bytes)
        encrypted_str = encrypted_bytes.decode()
        
        logger.debug("Successfully encrypted API key, length: %d", len(encrypted_str))
        return encrypted_str

    except EncryptionError:
        raise
    except Exception as e:
        logger.error("Encryption error: %s", str(e))
        raise EncryptionError(f"Failed to encrypt API key: {str(e)}")


def decrypt_api_key(encrypted_key: str, encryption_key: str) -> str:
    """Decrypt API key using Fernet symmetric encryption."""
    import os
    if os.environ.get('FLASK_ENV') == 'development':
        logger.debug("Development environment detected, skipping decryption")
        return encrypted_key
    try:
        if not encrypted_key:
            raise EncryptionError("Cannot decrypt: Encrypted key is empty")
        if not encryption_key:
            raise EncryptionError("Cannot decrypt: Encryption key is missing")

        logger.debug("Starting decryption - Encrypted key length: %d, Encryption key length: %d",
                     len(encrypted_key), len(encryption_key))

        # Normalize encryption key
        key_bytes = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
        
        # Ensure it's 32 bytes for Fernet
        decoded_key = base64.urlsafe_b64decode(key_bytes)
        if len(decoded_key) != 32:
            logger.error("Invalid key length after decoding: %d bytes", len(decoded_key))
            raise EncryptionError("Encryption key must decode to 32 bytes")
            
        # Create Fernet instance
        cipher_suite = Fernet(key_bytes)
        
        # Ensure consistent encrypted key encoding
        encrypted_bytes = encrypted_key.encode() if isinstance(encrypted_key, str) else encrypted_key
        logger.debug("Raw encrypted bytes length: %d", len(encrypted_bytes))

        # Log format details
        try:
            logger.debug("Encrypted key format check - Standard base64: %s",
                         all(c in b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
                             for c in encrypted_bytes))
            logger.debug("Encrypted key format check - URL-safe base64: %s",
                         all(c in b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_='
                             for c in encrypted_bytes))
        except Exception as e:
            logger.debug("Format check failed: %s", str(e))

        errors = []
        
        # First try direct decryption
        try:
            logger.debug("Attempting direct decryption")
            decrypted_key = cipher_suite.decrypt(encrypted_bytes)
            logger.debug("Successfully decrypted API key")
            return decrypted_key.decode()
        except Exception as e:
            errors.append(("Direct decryption", str(e)))
            logger.debug("Direct decryption failed: %s", str(e))

        # Try url-safe base64 normalization
        try:
            normalized = base64.urlsafe_b64encode(base64.urlsafe_b64decode(encrypted_bytes))
            logger.debug("URL-safe normalization successful, attempting decryption")
            return cipher_suite.decrypt(normalized).decode()
        except Exception as e:
            errors.append(("URL-safe normalization", str(e)))
            logger.debug("URL-safe normalization failed: %s", str(e))

        # Try standard base64 normalization
        try:
            normalized = base64.b64encode(base64.b64decode(encrypted_bytes))
            logger.debug("Standard base64 normalization successful, attempting decryption")
            return cipher_suite.decrypt(normalized).decode()
        except Exception as e:
            errors.append(("Standard base64 normalization", str(e)))
            logger.debug("Standard base64 normalization failed: %s", str(e))

        # All attempts failed
        logger.error("All decryption attempts failed:")
        for attempt, error in errors:
            logger.error("%s failed: %s", attempt, error)
        
        try:
            logger.error("Original encrypted key: %s", base64.b64encode(encrypted_bytes).decode())
        except Exception as e:
            logger.error("Could not encode key for logging: %s", str(e))
            
        raise EncryptionError("Invalid or corrupted encrypted key - all decryption attempts failed")

    except EncryptionError:
        raise
    except Exception as e:
        logger.error("Decryption error: %s", str(e))
        raise EncryptionError(f"Failed to decrypt API key: {str(e)}")
