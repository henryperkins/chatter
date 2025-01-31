# ADR 003: Data Security and Storage Architecture

## Status
Proposed

## Context
The chat application handles sensitive user data, conversation history, and model interactions. We need to ensure:
- End-to-end encryption for messages
- Secure file storage
- Efficient data retrieval
- Compliance with data protection regulations
- Scalable storage solutions

## Decision
We propose the following security and storage architecture:

### 1. Database Schema

```sql
-- Users and Authentication
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,
    settings JSONB DEFAULT '{}'::jsonb
);

-- Encryption Keys
CREATE TABLE encryption_keys (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    public_key TEXT NOT NULL,
    encrypted_private_key TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    rotated_at TIMESTAMP WITH TIME ZONE,
    active BOOLEAN DEFAULT true
);

-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    model_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    encrypted_key TEXT NOT NULL
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    role VARCHAR(50) NOT NULL,
    encrypted_content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    token_count INTEGER,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Files
CREATE TABLE files (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    conversation_id UUID REFERENCES conversations(id),
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    size BIGINT NOT NULL,
    encrypted_key TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Token Usage
CREATE TABLE token_usage (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    conversation_id UUID REFERENCES conversations(id),
    model_id VARCHAR(100) NOT NULL,
    tokens_used INTEGER NOT NULL,
    cost DECIMAL(10,6) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Encryption Strategy

```python
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

class EncryptionManager:
    def __init__(self):
        self.rsa_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        self.fernet_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.fernet_key)

    def encrypt_message(self, message: str, public_key: bytes) -> dict:
        """Encrypt a message with a new symmetric key."""
        message_key = Fernet.generate_key()
        cipher_suite = Fernet(message_key)

        # Encrypt message content
        encrypted_content = cipher_suite.encrypt(message.encode())

        # Encrypt message key with recipient's public key
        encrypted_key = public_key.encrypt(
            message_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        return {
            'encrypted_content': encrypted_content,
            'encrypted_key': encrypted_key
        }

    def decrypt_message(self, encrypted_data: dict, private_key: bytes) -> str:
        """Decrypt a message using the private key."""
        # Decrypt the message key
        message_key = private_key.decrypt(
            encrypted_data['encrypted_key'],
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # Decrypt the content
        cipher_suite = Fernet(message_key)
        decrypted_content = cipher_suite.decrypt(encrypted_data['encrypted_content'])

        return decrypted_content.decode()
```

### 3. File Storage

```python
from typing import BinaryIO
import boto3
from botocore.config import Config

class SecureFileStorage:
    def __init__(self):
        self.s3 = boto3.client('s3',
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            )
        )
        self.bucket = 'secure-chat-files'

    async def upload_file(self,
                         file: BinaryIO,
                         user_id: str,
                         encryption_key: bytes) -> dict:
        """Upload an encrypted file to storage."""
        # Generate unique file path
        file_path = f"{user_id}/{uuid.uuid4()}"

        # Encrypt file content
        encrypted_content = self.encrypt_file(file, encryption_key)

        # Upload to S3
        await self.s3.upload_fileobj(
            encrypted_content,
            self.bucket,
            file_path,
            ExtraArgs={
                'ServerSideEncryption': 'AES256',
                'Metadata': {
                    'user-id': user_id
                }
            }
        )

        return {
            'storage_path': file_path,
            'size': len(encrypted_content)
        }

    async def get_file(self,
                       storage_path: str,
                       encryption_key: bytes) -> BinaryIO:
        """Retrieve and decrypt a file."""
        # Download from S3
        encrypted_content = await self.s3.get_object(
            Bucket=self.bucket,
            Key=storage_path
        )

        # Decrypt content
        return self.decrypt_file(encrypted_content, encryption_key)
```

### 4. Data Retention and Cleanup

```python
class DataRetentionManager:
    def __init__(self):
        self.retention_periods = {
            'conversations': timedelta(days=90),
            'files': timedelta(days=30),
            'usage_logs': timedelta(days=365)
        }

    async def cleanup_expired_data(self):
        """Remove expired data based on retention policies."""
        now = datetime.utcnow()

        # Clean up conversations
        await self.db.execute("""
            DELETE FROM conversations
            WHERE updated_at < $1
            AND NOT metadata->>'retain' = 'true'
        """, now - self.retention_periods['conversations'])

        # Clean up files
        await self.db.execute("""
            DELETE FROM files
            WHERE created_at < $1
            AND NOT metadata->>'retain' = 'true'
        """, now - self.retention_periods['files'])

        # Clean up usage logs
        await self.db.execute("""
            DELETE FROM token_usage
            WHERE timestamp < $1
        """, now - self.retention_periods['usage_logs'])
```

## Consequences

### Positive
- End-to-end encryption for all messages
- Secure file storage with encryption
- Clear data retention policies
- Efficient data retrieval
- Scalable storage solution

### Negative
- Increased system complexity
- Key management overhead
- Performance impact of encryption
- Storage costs for encrypted data

### Neutral
- Need for key rotation procedures
- Regular security audits required
- Backup strategy complexity

## Implementation Plan

### Phase 1: Database Setup
1. Implement new schema
2. Create migration scripts
3. Set up indexes
4. Implement backup strategy

### Phase 2: Encryption
1. Implement key management
2. Add message encryption
3. Set up key rotation
4. Add audit logging

### Phase 3: File Storage
1. Set up S3 buckets
2. Implement file encryption
3. Add upload/download handlers
4. Set up cleanup jobs

### Phase 4: Monitoring
1. Add security monitoring
2. Implement usage tracking
3. Set up alerts
4. Create audit reports

## Success Metrics

1. Security
- Zero data breaches
- 100% message encryption
- Regular security audits
- Key rotation compliance

2. Performance
- < 100ms encryption overhead
- < 1s file upload time
- < 500ms file download time
- 99.99% availability

3. Maintenance
- Automated key rotation
- Regular data cleanup
- Backup verification
- Audit log completeness

## References

- [NIST Encryption Guidelines](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-175Br1.pdf)
- [AWS S3 Security Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html)
- [GDPR Compliance](https://gdpr.eu/data-protection/)
- [Database Encryption Patterns](https://docs.microsoft.com/en-us/azure/architecture/patterns/confidential-computing)
