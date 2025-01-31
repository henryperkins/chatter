import base64
from cryptography.fernet import Fernet
from config import Config

class EncryptionError(Exception):
    pass

def encrypt_api_key(api_key: str) -> str:
    try:
        encryption_key = Config.ENCRYPTION_KEY.encode()
        fernet = Fernet(encryption_key)
        encrypted_key = fernet.encrypt(api_key.encode())
        return encrypted_key.decode()
    except Exception as e:
        raise EncryptionError(f"Failed to encrypt API key: {str(e)}")

def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an encrypted API key using the configured encryption key.

    Args:
        encrypted_key: The encrypted API key as a string

    Returns:
        The decrypted API key as a string

    Raises:
        EncryptionError: If decryption fails
    """
    try:
        encryption_key = Config.ENCRYPTION_KEY.encode()
        fernet = Fernet(encryption_key)
        decrypted_key = fernet.decrypt(encrypted_key.encode())
        return decrypted_key.decode()
    except Exception as e:
        raise EncryptionError(f"Failed to decrypt API key: {str(e)}")
