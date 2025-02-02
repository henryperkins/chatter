"""
azure_search_config.py

This module provides configuration and utilities for Azure AI Search integration.
"""

import os
import logging
from typing import Dict, Any, Optional
import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class AzureSearchConfig:
    def __init__(self):
        # Required Azure AI Search settings
        # Core settings
        self.search_endpoint = os.getenv('AZURE_SEARCH_ENDPOINT')
        self.search_key = os.getenv('AZURE_SEARCH_KEY')
        self.search_index_name = os.getenv('AZURE_SEARCH_INDEX_NAME', 'chatterindex')
        self.api_version = os.getenv('AZURE_SEARCH_API_VERSION', '2023-11-01')

        # Service configuration
        self.replica_count = int(os.getenv('AZURE_SEARCH_REPLICA_COUNT', '2'))
        self.partition_count = int(os.getenv('AZURE_SEARCH_PARTITION_COUNT', '1'))
        self.hosting_mode = os.getenv('AZURE_SEARCH_HOSTING_MODE', 'default')
        self.semantic_search = os.getenv('AZURE_SEARCH_SEMANTIC_SEARCH', 'free')

        # Validate required settings
        if not all([self.search_endpoint, self.search_key]):
            raise ValueError(
                "Missing required Azure AI Search configuration. "
                "Please set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY environment variables."
            )

    def create_search_index(self) -> Dict[str, Any]:
        """
        Create or update the search index for file content.
        """
        try:
            # Define the service configuration
            service_config = {
                "name": self.search_index_name,
                "replicaCount": self.replica_count,
                "partitionCount": self.partition_count,
                "hostingMode": self.hosting_mode.capitalize(),
                "semanticSearch": self.semantic_search,
                "networkRuleSet": {
                    "ipRules": [],
                    "bypass": "None"
                },
                "fields": [
                    {
                        "name": "id",
                        "type": "Edm.String",
                        "key": True,
                        "searchable": False
                    },
                    {
                        "name": "content",
                        "type": "Edm.String",
                        "searchable": True,
                        "filterable": False,
                        "sortable": False,
                        "facetable": False,
                        "analyzer": "standard.lucene"
                    },
                    {
                        "name": "filepath",
                        "type": "Edm.String",
                        "searchable": True,
                        "filterable": True,
                        "sortable": True,
                        "facetable": False
                    },
                    {
                        "name": "title",
                        "type": "Edm.String",
                        "searchable": True,
                        "filterable": True,
                        "sortable": True,
                        "facetable": False
                    },
                    {
                        "name": "url",
                        "type": "Edm.String",
                        "searchable": True,
                        "filterable": True,
                        "sortable": True,
                        "facetable": False
                    },
                    {
                        "name": "metadata",
                        "type": "Edm.String",
                        "searchable": True,
                        "filterable": True,
                        "sortable": False,
                        "facetable": False
                    }
                ],
                "semantic": {
                    "configurations": [
                        {
                            "name": "default",
                            "prioritizedFields": {
                                "titleField": {
                                    "fieldName": "title"
                                },
                                "prioritizedContentFields": [
                                    {
                                        "fieldName": "content"
                                    }
                                ],
                                "prioritizedKeywordsFields": [
                                    {
                                        "fieldName": "metadata"
                                    }
                                ]
                            }
                        }
                    ]
                },
                "encryptionWithCmk": {
                    "enforcement": "Unspecified"
                },
                "authOptions": {
                    "apiKeyOnly": {}
                }
            }

            # Create or update the index
            headers = {
                'Content-Type': 'application/json',
                'api-key': self.search_key
            }

            response = requests.put(
                f"{self.search_endpoint}/indexes/{self.search_index_name}?api-version={self.api_version}",
                headers=headers,
                json=index_schema
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to create search index: {str(e)}")
            raise

    def index_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Index a document in Azure AI Search.

        Args:
            document: Document to index containing id, content, filepath, title, etc.

        Returns:
            Response from Azure AI Search
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'api-key': self.search_key
            }

            # Prepare the document for indexing
            index_payload = {
                "value": [document]
            }

            response = requests.post(
                f"{self.search_endpoint}/indexes/{self.search_index_name}/docs/index?api-version={self.api_version}",
                headers=headers,
                json=index_payload
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to index document: {str(e)}")
            raise

    def search_documents(self, query: str, filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Search documents in the index.

        Args:
            query: Search query string
            filter: Optional OData filter string

        Returns:
            Search results from Azure AI Search
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'api-key': self.search_key
            }

            # Prepare the search request
            search_payload = {
                "search": query,
                "select": "id,content,filepath,title,url,metadata",
                "orderby": "title",
                "queryType": "semantic",
                "semanticConfiguration": "default",
                "captions": "extractive",
                "answers": "extractive",
                "count": True
            }
            if filter:
                search_payload["filter"] = filter

            response = requests.post(
                f"{self.search_endpoint}/indexes/{self.search_index_name}/docs/search?api-version={self.api_version}",
                headers=headers,
                json=search_payload
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to search documents: {str(e)}")
            raise
