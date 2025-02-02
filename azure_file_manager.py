"""
azure_file_manager.py

This module provides classes for handling files with Azure OpenAI models,
including vector store integration and chat completions with file capabilities.
"""

import os
import time
import json
import logging
import requests
from typing import List, Optional, Dict, Any, Union
from functools import wraps

logger = logging.getLogger(__name__)

class FileProcessingError(Exception):
    """Custom exception for file processing errors"""
    pass

def safe_file_processing(func):
    """Decorator for safe file processing with proper error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)

            if isinstance(result, dict) and result.get('error'):
                raise FileProcessingError(f"API Error: {result['error']}")

            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Network Error in {func.__name__}: {str(e)}")
            raise FileProcessingError(f"Network Error: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error in {func.__name__}: {str(e)}")
            raise FileProcessingError("Invalid JSON response")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            raise FileProcessingError(f"Unexpected error: {str(e)}")
    return wrapper

class AzureOpenAIFileManager:
    """Handles file operations for Azure OpenAI models"""

    def __init__(self, endpoint: str, api_key: str, api_version: str = "2025-01-01-preview"):
        self.endpoint = endpoint
        self.api_key = api_key
        self.api_version = api_version
        self.base_url = f"https://{endpoint}/openai"
        self.headers = {
            "api-key": api_key,
            "Content-Type": "application/json"
        }

    @safe_file_processing
    def create_vector_store(self, name: str, file_ids: List[str], chunking_strategy: Optional[Dict] = None) -> dict:
        """
        Create a vector store for file search.

        Args:
            name: Name of the vector store
            file_ids: List of file IDs to include
            chunking_strategy: Optional custom chunking strategy

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/vector_stores?api-version={self.api_version}"

        if not chunking_strategy:
            chunking_strategy = {
                "type": "static",
                "static": {
                    "max_chunk_size_tokens": 1000,
                    "chunk_overlap_tokens": 100
                }
            }

        payload = {
            "name": name,
            "file_ids": file_ids,
            "chunking_strategy": chunking_strategy
        }

        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    @safe_file_processing
    def upload_file_batch(self, vector_store_id: str, file_ids: List[str], chunking_strategy: Optional[Dict] = None) -> dict:
        """
        Upload a batch of files to a vector store.

        Args:
            vector_store_id: ID of the vector store
            file_ids: List of file IDs to upload
            chunking_strategy: Optional custom chunking strategy

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/vector_stores/{vector_store_id}/file_batches?api-version={self.api_version}"

        payload = {
            "file_ids": file_ids,
            "chunking_strategy": chunking_strategy or {"type": "auto"}
        }

        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    @safe_file_processing
    def get_vector_store_status(self, vector_store_id: str) -> dict:
        """
        Check vector store status.

        Args:
            vector_store_id: ID of the vector store

        Returns:
            Status information as dictionary
        """
        url = f"{self.base_url}/vector_stores/{vector_store_id}?api-version={self.api_version}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    @safe_file_processing
    def list_vector_store_files(self, vector_store_id: str) -> dict:
        """
        List files in a vector store.

        Args:
            vector_store_id: ID of the vector store

        Returns:
            List of files as dictionary
        """
        url = f"{self.base_url}/vector_stores/{vector_store_id}/files?api-version={self.api_version}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def wait_for_vector_store_ready(self, vector_store_id: str, timeout: int = 300, interval: int = 5) -> bool:
        """
        Wait for vector store to be ready.

        Args:
            vector_store_id: ID of the vector store
            timeout: Maximum time to wait in seconds
            interval: Check interval in seconds

        Returns:
            True if ready, False if timeout
        """
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            try:
                status = self.get_vector_store_status(vector_store_id)
                if status['status'] == 'completed':
                    return True
                elif status['status'] == 'failed':
                    raise FileProcessingError(f"Vector store processing failed: {status.get('error', 'Unknown error')}")
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error checking vector store status: {str(e)}")
                raise
        return False

class AzureOpenAIChatWithFiles:
    """Handles chat completions with file capabilities"""

    def __init__(self, endpoint: str, api_key: str, deployment_id: str):
        self.file_manager = AzureOpenAIFileManager(endpoint, api_key)
        self.deployment_id = deployment_id
        self.base_url = f"https://{endpoint}/openai"
        self.headers = {
            "api-key": api_key,
            "Content-Type": "application/json"
        }

    @safe_file_processing
    def chat_with_file_search(
        self,
        messages: List[dict],
        vector_store_id: str,
        top_n: int = 5,
        strictness: int = 3,
        filter: Optional[dict] = None,
        temperature: float = 0.7
    ) -> dict:
        """
        Chat completion with file search capability.

        Args:
            messages: List of chat messages
            vector_store_id: ID of the vector store to search
            top_n: Number of top documents to retrieve
            strictness: Search strictness (1-5)
            filter: Optional search filter
            temperature: Temperature for response generation

        Returns:
            Chat completion response as dictionary
        """
        url = f"{self.base_url}/deployments/{self.deployment_id}/chat/completions?api-version=2025-01-01-preview"

        payload = {
            "messages": messages,
            "data_sources": [
                {
                    "type": "azure_search",
                    "parameters": {
                        "vector_store_ids": [vector_store_id],
                        "top_n_documents": top_n,
                        "strictness": strictness,
                        "filter": filter
                    }
                }
            ],
            "temperature": temperature,
            "tools": [
                {
                    "type": "file_search"
                }
            ]
        }

        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    @safe_file_processing
    def chat_with_code_interpreter(
        self,
        messages: List[dict],
        file_ids: List[str],
        temperature: float = 0.7
    ) -> dict:
        """
        Chat completion with code interpreter and file access.

        Args:
            messages: List of chat messages
            file_ids: List of file IDs to make available
            temperature: Temperature for response generation

        Returns:
            Chat completion response as dictionary
        """
        url = f"{self.base_url}/deployments/{self.deployment_id}/chat/completions?api-version=2025-01-01-preview"

        payload = {
            "messages": messages,
            "temperature": temperature,
            "tools": [
                {
                    "type": "code_interpreter"
                }
            ],
            "tool_resources": {
                "code_interpreter": {
                    "file_ids": file_ids
                }
            }
        }

        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
