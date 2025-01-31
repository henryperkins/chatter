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
