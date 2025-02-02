#!/usr/bin/env python3
"""
Background script to index uploaded files in Azure AI Search.
This script can be run periodically to process any unindexed files.
"""

import os
import sys
import logging
from pathlib import Path
import json
import time

# Add project root to Python path
project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, project_root)

from models.uploaded_file import UploadedFile
from azure_search_config import AzureSearchConfig
import hashlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def process_unindexed_files():
    """Process all unindexed files and add them to Azure AI Search."""
    try:
        # Initialize Azure Search
        search_config = AzureSearchConfig()

        # Get all unindexed files
        unindexed_files = UploadedFile.get_unindexed_files()
        logger.info(f"Found {len(unindexed_files)} unindexed files")

        for file in unindexed_files:
            try:
                # Generate a unique document ID
                doc_id = hashlib.sha256(
                    f"{file.filepath}_{file.size}".encode()
                ).hexdigest()

                # Read file content
                with open(file.filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Create the search document
                document = {
                    "id": doc_id,
                    "title": file.filename,
                    "content": content,
                    "filepath": file.filepath,
                    "url": f"file://{file.filepath}",  # Local file URL
                    "metadata": json.dumps({
                        "size": file.size,
                        "mime_type": file.mime_type,
                        "description": file.description or "",
                        "last_modified": time.time()
                    })
                }

                # Index the document
                search_config.index_document(document)
                logger.info(f"Successfully indexed file: {file.filename}")

                # Update file status
                UploadedFile.update_search_status(
                    file_id=file.id,
                    status='indexed',
                    search_id=doc_id
                )

            except Exception as e:
                logger.error(f"Failed to index file {file.filename}: {str(e)}")
                # Mark file as failed
                UploadedFile.update_search_status(
                    file_id=file.id,
                    status='failed'
                )
                continue

    except Exception as e:
        logger.error(f"Error in indexing process: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        process_unindexed_files()
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")
        sys.exit(1)
