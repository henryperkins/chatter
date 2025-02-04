# utils/encryption.py

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
        logger.error(f"Failed to encrypt API key: {e}")
        raise EncryptionError(f"Failed to encrypt API key: {e}")


def decrypt_api_key(encrypted_key: str, encryption_key: str) -> str:
    """
    Decrypt an API key.

    This function always attempts decryption using Fernet.
    If decryption fails due to an InvalidToken error, we log the issue
    and return the provided key (assuming it might already be plaintext).
    """
    try:
        if not encrypted_key:
            raise ValueError("Encrypted key cannot be empty")

        f = Fernet(encryption_key.encode())
        # Attempt decryption; if it fails, log the error and return the key as plaintext.
        try:
            return f.decrypt(encrypted_key.encode()).decode()
        except InvalidToken:
            logger.error(
                "Invalid or corrupted encrypted key – treating key as plaintext."
            )
            return encrypted_key
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {e}")
        raise EncryptionError(f"Failed to decrypt API key: {e}")
