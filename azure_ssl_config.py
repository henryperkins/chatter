"""Azure TLS/SSL configuration for Python"""
import os
import ssl
import certifi

def get_ssl_context():
    """Get SSL context with proper cert configuration"""
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    
    # Use SSL_CERT_FILE from env or fallback to certifi
    ssl_cert = os.getenv('SSL_CERT_FILE') or certifi.where()
    ssl_context.load_verify_locations(cafile=ssl_cert)
    
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.check_hostname = True
    return ssl_context

# Required for Azure PostgreSQL and OpenAI
AZURE_TLS_CONTEXT = get_ssl_context()
