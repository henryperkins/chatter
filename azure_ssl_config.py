"""Azure TLS/SSL configuration for Python"""
import ssl
import certifi

# Required for Azure PostgreSQL and OpenAI
AZURE_TLS_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
AZURE_TLS_CONTEXT.load_verify_locations(cafile=certifi.where())
AZURE_TLS_CONTEXT.verify_mode = ssl.CERT_REQUIRED
AZURE_TLS_CONTEXT.check_hostname = True  # Use False for private endpoints
