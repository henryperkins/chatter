import base64
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""

    pass


def encrypt_api_key(api_key: str, encryption_key: str) -> str:
    """No-op encryption"""
    return api_key  # Simply return the plaintext key


def decrypt_api_key(encrypted_key: str, encryption_key: str) -> str:
    """No-op decryption"""
    return encrypted_key  # Return the input directly
