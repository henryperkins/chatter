import logging

# Remove unneeded imports:
# from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""

    pass


def encrypt_api_key(api_key: str, encryption_key: str) -> str:
    """Return API key in plaintext (encryption removed)."""
    return api_key


def decrypt_api_key(encrypted_key: str, encryption_key: str) -> str:
    """Return API key in plaintext (decryption removed)."""
    return encrypted_key
