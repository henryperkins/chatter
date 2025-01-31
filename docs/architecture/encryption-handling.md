# API Key Encryption Architecture

## Current Implementation

The application currently handles API key encryption through a centralized utility in `utils/encryption.py`, but lacks centralized decryption handling. This has led to:

1. Inconsistent encryption/decryption implementations
2. Duplicate code for key formatting and validation
3. Potential security vulnerabilities due to inconsistent handling

## Issues Identified

1. **Decryption Failures**
   - Multiple "Failed to decrypt API key" errors occurring in model.py
   - Root cause: Inconsistent encryption key formatting between encryption and decryption operations
   - The encryption utility properly formats keys, but model.py attempts its own key formatting

2. **Code Duplication**
   - Encryption key formatting logic exists in both:
     - utils/encryption.py (for encryption)
     - model.py (for decryption)
   - This violates DRY principles and leads to maintenance issues

## Proposed Solution

1. **Centralize Decryption**
   - Add decrypt_api_key function to utils/encryption.py
   - Use consistent key formatting across both encryption and decryption
   - Handle all encryption-related errors in one place

2. **Refactor Model Class**
   - Update model.py to use the centralized encryption utilities
   - Remove duplicate key formatting logic
   - Improve error handling and logging

3. **Standardize Error Handling**
   - Use custom EncryptionError for all encryption-related errors
   - Provide clear error messages for debugging
   - Maintain proper logging of encryption/decryption failures

## Implementation Steps

1. Add decryption functionality to utils/encryption.py:
```python
def decrypt_api_key(encrypted_key: str) -> str:
    try:
        encryption_key = Config.ENCRYPTION_KEY.encode()
        fernet = Fernet(encryption_key)
        decrypted_key = fernet.decrypt(encrypted_key.encode())
        return decrypted_key.decode()
    except Exception as e:
        raise EncryptionError(f"Failed to decrypt API key: {str(e)}")
```

2. Update model.py to use centralized encryption utilities:
```python
from utils.encryption import decrypt_api_key, EncryptionError

# In get_by_id method:
try:
    model_dict["api_key"] = decrypt_api_key(encrypted_key)
except EncryptionError as e:
    logger.error(str(e))
    model_dict["api_key"] = ""
```

## Security Considerations

1. **Key Management**
   - ENCRYPTION_KEY is properly validated in Config class
   - Base64 encoding is handled consistently
   - Failed decryption attempts are logged but don't expose sensitive data

2. **Error Handling**
   - Encryption failures don't expose the original API key
   - Decryption failures return empty strings rather than partial/corrupted data

## Additional Notes

The 405 Method Not Allowed errors for liveonshuffle.com are unrelated to the encryption issues and are being properly handled by the application's error handlers. These represent external attempts to access endpoints with incorrect HTTP methods, which is expected behavior for public-facing applications.
