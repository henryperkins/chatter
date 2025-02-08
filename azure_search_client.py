"""
azure_search_client.py

This module provides advanced Azure Cognitive Search integration with Azure OpenAI API,
supporting semantic, vector, and hybrid search capabilities.
"""

import os
import time
import logging
from typing import Dict, List, Optional, Any
import requests
from functools import wraps

logger = logging.getLogger(__name__)

class SearchError(Exception):
    """Custom exception for search-related errors"""
    pass

class SearchMonitoring:
    """Handles search query monitoring and metrics"""

    def __init__(self):
        self.metrics = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "average_latency": 0
        }

    def track_query(self, success: bool, latency: float):
        """Track search query metrics"""
        self.metrics["total_queries"] += 1
        if success:
            self.metrics["successful_queries"] += 1
        else:
            self.metrics["failed_queries"] += 1

        # Update rolling average latency
        self.metrics["average_latency"] = (
            (self.metrics["average_latency"] * (self.metrics["total_queries"] - 1) + latency)
            / self.metrics["total_queries"]
        )

def safe_search_query(func):
    """Decorator for safe search query execution with monitoring"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            latency = time.time() - start_time

            # Track metrics
            SearchMonitoring().track_query(True, latency)

            return result
        except Exception as e:
            latency = time.time() - start_time
            SearchMonitoring().track_query(False, latency)
            logger.error(f"Search query failed: {str(e)}")
            raise SearchError(f"Search query failed: {str(e)}")

    return wrapper

class AzureSearchConfig:
    """Configuration for Azure Cognitive Search"""

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        api_key: Optional[str] = None,
        use_managed_identity: bool = False,
        managed_identity_id: Optional[str] = None
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.index_name = index_name
        self.use_managed_identity = use_managed_identity
        self.managed_identity_id = managed_identity_id

class AzureSearchFields:
    """Manages field mappings for different search scenarios"""

    def __init__(self):
        self.field_mappings = {
            "default": {
                "title_field": "title",
                "url_field": "url",
                "content_fields": ["content"],
                "vector_fields": ["contentvector"]
            },
            "hybrid": {
                "title_field": "title",
                "url_field": "url",
                "content_fields": ["content", "summary"],
                "vector_fields": ["contentvector", "summaryvector"]
            }
        }

    def get_mapping(self, mapping_type: str = "default") -> Dict[str, Any]:
        """Get field mapping configuration"""
        return self.field_mappings.get(mapping_type, self.field_mappings["default"])

class AzureSearchChatExtension:
    """Handles Azure Search integration with chat completions"""

    def __init__(self, search_config: AzureSearchConfig):
        self.config = search_config
        self.fields = AzureSearchFields()

    def get_search_parameters(
        self,
        query_type: str = "semantic",
        top_n: int = 5,
        strictness: int = 3,
        field_mapping_type: str = "default",
        semantic_config: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Generate Azure Search parameters for chat extensions.

        Args:
            query_type: Type of search (semantic, vector, or vector_semantic_hybrid)
            top_n: Number of top results to return
            strictness: Search strictness (1-5)
            field_mapping_type: Type of field mapping to use
            semantic_config: Optional semantic configuration name
            filters: Optional filters to apply to the search
        """
        params = {
            "type": "azure_search",
            "parameters": {
                "endpoint": self.config.endpoint,
                "index_name": self.config.index_name,
                "query_type": query_type,
                "top_n_documents": top_n,
                "strictness": strictness,
                "fields_mapping": self.fields.get_mapping(field_mapping_type),
                "in_scope": True
            }
        }

        # Add authentication
        if self.config.use_managed_identity:
            params["parameters"]["authentication"] = {
                "type": "user_assigned_managed_identity" if self.config.managed_identity_id else "system_assigned_managed_identity"
            }
            if self.config.managed_identity_id:
                params["parameters"]["authentication"]["managed_identity_resource_id"] = self.config.managed_identity_id
        elif self.config.api_key:
            params["parameters"]["authentication"] = {
                "type": "api_key",
                "key": self.config.api_key
            }

        # Add semantic configuration if provided
        if semantic_config and query_type in ["semantic", "vector_semantic_hybrid"]:
            params["parameters"]["semantic_configuration"] = semantic_config

        # Add filters if provided
        if filters:
            params["parameters"]["filter"] = " and ".join([f"{k} eq '{v}'" for k, v in filters.items()])

        # Add embedding configuration for vector search
        if query_type in ["vector", "vector_semantic_hybrid"]:
            params["parameters"]["embedding_dependency"] = {
                "type": "deployment_name",
                "deployment_name": os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
            }

        return params

class AzureOpenAI:
    def __init__(self, azure_endpoint, api_key, api_version):
        self.azure_endpoint = azure_endpoint
        self.api_key = api_key
        self.api_version = api_version
        self.chat = self.Chat(self.azure_endpoint, self.api_key, self.api_version)

    class Chat:
        def __init__(self, azure_endpoint, api_key, api_version):
            self.azure_endpoint = azure_endpoint.rstrip("/")
            self.api_key = api_key
            self.api_version = api_version
            self.completions = self.Completions(self.azure_endpoint, self.api_key, self.api_version)

        class Completions:
            def __init__(self, endpoint, api_key, api_version):
                self.endpoint = endpoint
                self.api_key = api_key
                self.api_version = api_version

            def create(self, model, messages, temperature, max_tokens, stream):
                import requests
                url = f"{self.endpoint}/openai/deployments/{model}/chat/completions?api-version={self.api_version}"
                headers = {
                    "Content-Type": "application/json",
                    "api-key": self.api_key
                }
                payload = {
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": stream
                }
                response = requests.post(url, headers=headers, json=payload, stream=stream)
                response.raise_for_status()
                if stream:
                    # Stream text in small chunks
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            # Return partial text in a structure consistent with chat_routes.py
                            yield {
                                "choices": [
                                    {
                                        "delta": {
                                            "content": chunk.decode('utf-8', errors='replace')
                                        }
                                    }
                                ]
                            }
                else:
                    # Non-streaming response
                    yield response.json()

class AzureOpenAISearchChat:
    """Handles chat completions with Azure Search integration"""

    def __init__(
        self,
        openai_endpoint: str,
        openai_key: str,
        deployment_id: str,
        search_config: AzureSearchConfig
    ):
        self.openai_endpoint = openai_endpoint
        self.openai_key = openai_key
        self.deployment_id = deployment_id
        self.search_extension = AzureSearchChatExtension(search_config)

    @safe_search_query
    def chat_with_search(
        self,
        messages: List[Dict[str, str]],
        query_type: str = "vector",
        temperature: float = 0.7,
        max_tokens: int = 800,
        top_n: int = 5,
        strictness: int = 3,
        semantic_config: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Chat completion with Azure Search integration.

        Args:
            messages: List of chat messages
            query_type: Type of search (semantic, vector, or vector_semantic_hybrid)
            temperature: Temperature for response generation
            max_tokens: Maximum tokens for completion
            top_n: Number of top results to return
            strictness: Search strictness (1-5)
            semantic_config: Optional semantic configuration name
            filters: Optional filters to apply to the search
        """
        url = f"https://{self.openai_endpoint}/openai/deployments/{self.deployment_id}/chat/completions?api-version=2025-01-01-preview"

        # Get search parameters
        search_params = self.search_extension.get_search_parameters(
            query_type=query_type,
            top_n=top_n,
            strictness=strictness,
            semantic_config=semantic_config,
            filters=filters
        )

        payload = {
            "messages": messages,
            "data_sources": [search_params],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "tools": [
                {
                    "type": "file_search",
                    "file_search": {
                        "max_num_results": top_n
                    }
                }
            ]
        }

        headers = {
            "api-key": self.openai_key,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Chat completion request failed: {str(e)}")
            raise SearchError(f"Chat completion request failed: {str(e)}")

def create_search_client(model_type: str = "gpt-4o") -> Optional[AzureOpenAISearchChat]:
    """
    Create a search-enabled chat client based on environment configuration.

    Args:
        model_type: Type of model to use (gpt-4o or o1)
    """
    try:
        # Get required environment variables
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_KEY")
        deployment_id = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "markdown-index")
        use_managed_identity = os.getenv("USE_MANAGED_IDENTITY", "false").lower() == "true"
        managed_identity_id = os.getenv("MANAGED_IDENTITY_RESOURCE_ID")

        if not all([endpoint, api_key, deployment_id, search_endpoint]):
            logger.error("Missing required environment variables for search client")
            return None

        # Create search configuration
        search_config = AzureSearchConfig(
            endpoint=search_endpoint,
            index_name=index_name,
            api_key=os.getenv("AZURE_SEARCH_KEY"),  # Optional when using managed identity
            use_managed_identity=use_managed_identity,
            managed_identity_id=managed_identity_id
        )

        # Create and return chat client
        return AzureOpenAISearchChat(
            openai_endpoint=endpoint,
            openai_key=api_key,
            deployment_id=deployment_id,
            search_config=search_config
        )

    except Exception as e:
        logger.error(f"Failed to create search client: {str(e)}")
        return None
