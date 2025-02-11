"""Azure TLS/SSL configuration for Python"""
import os
import ssl
import certifi

# Create default context for server authentication
AZURE_TLS_CONTEXT = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
AZURE_TLS_CONTEXT.verify_mode = ssl.CERT_REQUIRED
AZURE_TLS_CONTEXT.check_hostname = False  # Disabled for Azure private endpoints
AZURE_TLS_CONTEXT.load_verify_locations(cafile=certifi.where())
