"""
chat_api.py

This module provides functions for interacting with the Azure OpenAI API,
including sending chat messages and getting responses, as well as web scraping.
"""

import logging
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Union, Generator, Any
import requests
from bs4 import BeautifulSoup
from openai import AzureOpenAI
from azure_file_manager import AzureOpenAIChatWithFiles, AzureOpenAIFileManager
from azure_search_client import create_search_client, AzureOpenAISearchChat
from models.model import Model

# Type aliases for better readability
ResponseType = Union[Dict[str, Any], str, Generator[Dict[str, Any], None, None]]
ApiParams = Dict[str, Any]

logger = logging.getLogger(__name__)

# Initialize clients
_file_chat_client = None
_search_chat_client = None
_azure_client = None

def get_azure_client(api_key: str, api_endpoint: str, api_version: str) -> AzureOpenAI:
    """Get or create Azure OpenAI client with enhanced validation and error handling"""
    global _azure_client
    if _azure_client is None:
        try:
            # Validate inputs
            if not api_key or not api_key.strip():
                raise ValueError("API key cannot be empty")
            if not api_endpoint or not api_endpoint.strip():
                raise ValueError("API endpoint cannot be empty")
            if not api_version or not api_version.strip():
                raise ValueError("API version cannot be empty")

            # Validate API endpoint format
            if not api_endpoint.startswith(('http://', 'https://')):
                raise ValueError("API endpoint must start with http:// or https://")

            # Remove any trailing slashes from the endpoint
            api_endpoint = api_endpoint.rstrip('/')

            # Log the configuration being used (mask sensitive data)
            logger.debug("Initializing Azure OpenAI client with:")
            logger.debug(f"API Endpoint: {api_endpoint}")
            logger.debug(f"API Version: {api_version}")
            logger.debug(f"API Key: {api_key[:4]}...{api_key[-4:] if len(api_key) > 8 else '****'}")

            # Initialize the client with direct API key authentication
            _azure_client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=api_endpoint,
                api_version=api_version
            )

            # Test the client with a simple request
            try:
                _azure_client.models.list()
                logger.debug("Successfully tested Azure OpenAI client connection")
            except Exception as test_error:
                logger.error(f"Failed to test Azure OpenAI client: {str(test_error)}")
                _azure_client = None
                raise ValueError(f"Failed to validate Azure OpenAI client: {str(test_error)}")

            logger.debug("Successfully initialized Azure OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI client: {str(e)}")
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Failed to initialize Azure OpenAI client: {str(e)}")
    return _azure_client

def get_file_chat_client() -> Optional[AzureOpenAIChatWithFiles]:
    global _file_chat_client
    if _file_chat_client is None and os.getenv("AZURE_OPENAI_ENDPOINT"):
        try:
            _file_chat_client = AzureOpenAIChatWithFiles(
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                api_key=os.getenv("AZURE_OPENAI_KEY", ""),
                deployment_id=os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
            )
        except Exception as e:
            logger.error(f"Failed to initialize file chat client: {str(e)}")
    return _file_chat_client

def get_search_chat_client(model_type: str) -> Optional[AzureOpenAISearchChat]:
    """Get or create search-enabled chat client"""
    global _search_chat_client
    if _search_chat_client is None and os.getenv("AZURE_SEARCH_ENDPOINT"):
        try:
            _search_chat_client = create_search_client(model_type)
        except Exception as e:
            logger.error(f"Failed to initialize search chat client: {str(e)}")
    return _search_chat_client

def get_azure_response(
    messages: List[Dict[str, str]],
    deployment_name: Optional[str] = None,
    max_completion_tokens: Optional[int] = None,
    api_endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: Optional[str] = None,
    model_type: Optional[str] = None,
    requires_o1_handling: bool = False,
    reasoning_effort: str = 'medium',
    store_completion: bool = False,
    response_format: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 600,
    stream: bool = False,
    file_ids: Optional[List[str]] = None,
    vector_store_id: Optional[str] = None,
    use_code_interpreter: bool = False
) -> Union[Dict[str, Any], str, Generator]:
    try:
        # Add detailed debug logging
        logger.debug("Starting Azure API request with parameters:")
        logger.debug(f"Deployment name: {deployment_name}")
        logger.debug(f"API endpoint: {api_endpoint}")
        logger.debug(f"API version: {api_version}")
        logger.debug(f"Model type: {model_type}")
        logger.debug(f"Messages count: {len(messages)}")
        logger.debug(f"API key length: {len(api_key) if api_key else 0}")

        # Validate required parameters
        if not all([deployment_name, api_endpoint, api_key, api_version]):
            missing = []
            if not deployment_name: missing.append("deployment_name")
            if not api_endpoint: missing.append("api_endpoint")
            if not api_key: missing.append("api_key")
            if not api_version: missing.append("api_version")
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        try:
            # Initialize Azure OpenAI client
            client = get_azure_client(api_key, api_endpoint, api_version)

            # Log successful client initialization
            logger.debug("Successfully initialized Azure OpenAI client")

            # Prepare the completion parameters
            completion_params = {
                "model": deployment_name,
                "messages": messages,
                "stream": stream
            }

            # Get model capabilities
            model_caps = Model.PROVIDER_CAPABILITIES.get(model_type, {})

            # Set base parameters using model capabilities
            completion_params.update({
                "temperature": 1.0 if model_caps.get("fixed_temperature") else 0.7,
                "max_tokens": min(
                    max_completion_tokens or model_caps.get("max_tokens", 16384),
                    model_caps.get("max_tokens", 16384)
                )
            })

            # Add model-specific parameters based on capabilities
            if model_caps.get("requires_reasoning_effort"):
                completion_params.update({
                    "reasoning_effort": reasoning_effort,
                    "store_completion": store_completion
                })

            # Add response format if supported
            if model_caps.get("supports_json_mode") and response_format:
                completion_params["response_format"] = response_format

            # Handle streaming capability
            if stream and not model_caps.get("streaming", True):
                logger.warning(f"Streaming not supported for model type {model_type}, falling back to non-streaming")
                stream = False
                completion_params["stream"] = False

            # Log the final parameters
            logger.debug(f"Using model capabilities: {json.dumps(model_caps, indent=2)}")

            logger.debug(f"Completion parameters: {json.dumps(completion_params, indent=2)}")

            # Validate messages format
            if not isinstance(messages, list):
                raise ValueError("Messages must be a list")
            for msg in messages:
                if not isinstance(msg, dict) or 'role' not in msg or 'content' not in msg:
                    raise ValueError("Invalid message format")

            # Validate and sanitize messages
            sanitized_messages = []
            for msg in messages:
                if not isinstance(msg, dict):
                    raise ValueError(f"Invalid message format: {msg}")
                if 'role' not in msg or 'content' not in msg:
                    raise ValueError(f"Message missing required fields: {msg}")
                if msg['role'] not in ['system', 'user', 'assistant']:
                    raise ValueError(f"Invalid message role: {msg['role']}")
                if not isinstance(msg['content'], str):
                    raise ValueError(f"Message content must be string: {msg}")

                # Sanitize content
                sanitized_content = msg['content'].strip()
                if not sanitized_content:
                    continue  # Skip empty messages

                sanitized_messages.append({
                    'role': msg['role'],
                    'content': sanitized_content
                })

            if not sanitized_messages:
                raise ValueError("No valid messages provided")

            completion_params['messages'] = sanitized_messages

            # Make the API call
            if stream:
                stream_response = client.chat.completions.create(**completion_params)
                def generate():
                    try:
                        current_content = ""
                        last_error = None
                        consecutive_errors = 0
                        MAX_RETRIES = 3

                        for chunk in stream_response:
                            try:
                                if not hasattr(chunk.choices[0], 'delta'):
                                    logger.warning("Received chunk without delta")
                                    continue

                                delta = chunk.choices[0].delta

                                # Reset error counter on successful chunk
                                consecutive_errors = 0

                                # Handle system messages in stream
                                if hasattr(delta, 'role') and delta.role == 'system':
                                    continue

                                # Handle content updates
                                if hasattr(delta, 'content') and delta.content is not None:
                                    current_content += delta.content
                                    yield {
                                        "choices": [{
                                            "message": {
                                                "content": delta.content,
                                                "role": "assistant"
                                            },
                                            "finish_reason": None,
                                            "index": 0
                                        }],
                                        "created": int(datetime.now().timestamp()),
                                        "model": completion_params['model']
                                    }

                                # Handle end of stream
                                if hasattr(chunk.choices[0], 'finish_reason') and chunk.choices[0].finish_reason:
                                    yield {
                                        "choices": [{
                                            "message": {
                                                "content": current_content,
                                                "role": "assistant"
                                            },
                                            "finish_reason": chunk.choices[0].finish_reason,
                                            "index": 0
                                        }],
                                        "created": int(datetime.now().timestamp()),
                                        "model": completion_params['model']
                                    }

                            except Exception as chunk_error:
                                logger.error(f"Error processing chunk: {str(chunk_error)}")
                                consecutive_errors += 1
                                last_error = chunk_error

                                if consecutive_errors >= MAX_RETRIES:
                                    raise Exception(f"Too many consecutive errors: {str(last_error)}")
                                continue

                    except Exception as e:
                        logger.error(f"Error in stream processing: {str(e)}")
                        # Yield error message to client
                        yield {
                            "error": str(e),
                            "choices": [{
                                "message": {
                                    "content": f"An error occurred during streaming: {str(e)}",
                                    "role": "assistant"
                                },
                                "finish_reason": "error",
                                "index": 0
                            }],
                            "created": int(datetime.now().timestamp()),
                            "model": completion_params['model']
                        }
                return generate()
            else:
                response = client.chat.completions.create(**completion_params)

                # Validate response
                if not response:
                    raise ValueError("Empty response from API")
                if not hasattr(response, 'choices') or not response.choices:
                    raise ValueError("API returned no choices")
                if not hasattr(response.choices[0], 'message'):
                    raise ValueError("Invalid response format: missing message")
                if not hasattr(response.choices[0].message, 'content'):
                    raise ValueError("Invalid response format: missing content")
                if not response.choices[0].message.content.strip():
                    raise ValueError("Empty response content")

                return response.choices[0].message.content

        except Exception as client_error:
            logger.error(f"Error with Azure OpenAI client: {str(client_error)}")
            # Log additional error details if available
            if hasattr(client_error, 'response'):
                logger.error(f"Response status: {client_error.response.status_code}")
                logger.error(f"Response body: {client_error.response.text}")
            raise

    except Exception as e:
        logger.error(f"Unexpected error in get_azure_response: {str(e)}")
        raise Exception(f"An unexpected error occurred: {str(e)}")

def scrape_data(query: str) -> str:
    """
    Scrapes data from the web based on the given query.

    Args:
        query: The search query.

    Returns:
        The scraped data as a string.

    Raises:
        ValueError: If the query type is invalid.
    """
    if query.startswith("what's the weather in"):
        location = query.split("what's the weather in")[1].strip()
        return scrape_weather(location)
    elif query.startswith("search for"):
        search_term = query.split("search for")[1].strip()
        return scrape_search(search_term)
    else:
        raise ValueError("Invalid query type")

def scrape_weather(location: str) -> str:
    """
    Scrapes weather information for the given location from Google Search.

    Args:
        location: The location for which to scrape weather information.

    Returns:
        The weather information as a string.
    """
    url = f"https://www.google.com/search?q=weather+{location}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during web request for weather: {str(e)}")
        return "Could not retrieve weather information due to a network error."

    soup = BeautifulSoup(response.text, "html.parser")
    if weather_element := soup.find("div", class_="BNeawe"):
        weather = weather_element.text
        return f"The weather in {location} is: {weather}"
    else:
        logger.warning("Could not find weather information in the page.")
        return f"Could not retrieve weather information for {location}."

def scrape_search(search_term: str) -> str:
    """
    Scrapes search results for the given search term from Google Search.

    Args:
        search_term: The term to search for.

    Returns:
        The search results as a string.
    """
    url = f"https://www.google.com/search?q={search_term}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during web request for search: {str(e)}")
        return "Could not retrieve search results due to a network error."

    soup = BeautifulSoup(response.text, "html.parser")
    results = soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd")
    search_results = [result.text for result in results[:3]]

    return "Search results:\n" + "\n".join(search_results)

def upload_file_to_azure(file_content: bytes, file_name: str, content_type: str) -> Optional[str]:
    """
    Uploads a file to Azure Blob Storage.

    Args:
        file_content: The content of the file as bytes
        file_name: The name of the file
        content_type: The MIME type of the file

    Returns:
        The Azure file ID if successful, None otherwise
    """
    try:
        from azure.storage.blob import BlobServiceClient
        import os

        # Get Azure Storage connection string from environment
        connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
        container_name = os.getenv('AZURE_STORAGE_CONTAINER')

        if not connection_string or not container_name:
            logger.error("Azure Storage configuration missing")
            return None

        # Create the BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)

        # Get container client
        container_client = blob_service_client.get_container_client(container_name)

        # Generate a unique blob name
        import uuid
        blob_name = f"{uuid.uuid4()}-{file_name}"

        # Get blob client
        blob_client = container_client.get_blob_client(blob_name)

        # Upload the file
        blob_client.upload_blob(file_content, blob_type="BlockBlob", content_settings={
            "content_type": content_type
        })

        logger.info(f"Successfully uploaded file {file_name} to Azure Storage")
        return blob_name

    except Exception as e:
        logger.error(f"Error uploading file to Azure Storage: {str(e)}")
        return None
