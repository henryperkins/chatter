"""Module for Azure OpenAI API interaction and chat handling."""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Union, Generator, Any

import requests
from openai import AzureOpenAI

from logging_config import get_logger
from utils.encryption import decrypt_api_key
import base64
import hashlib
from config import Config
from azure_config import validate_model_config, create_client

logger = get_logger("chat_api")

# Type aliases
ResponseType = Union[Dict[str, Any], str, Generator[Dict[str, Any], None, None]]
Message = Dict[str, str]
ChatResponse = Dict[str, Any]


class ChatClient:
    """Manages chat interactions with Azure OpenAI API."""

    def __init__(self):
        self._azure_client = None
        self._file_chat_client = None
        self._search_chat_client = None
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )

    def get_azure_client(
        self, api_key: str, api_endpoint: str, api_version: str
    ) -> AzureOpenAI:
        """
        Get or create an Azure OpenAI client using create_client from azure_config.
        """
        if self._azure_client is None:
            self._azure_client = create_client(
                api_key=api_key, api_endpoint=api_endpoint, api_version=api_version
            )
        return self._azure_client

    def get_file_chat_client(self) -> Optional[Any]:
        """
        Get or create file chat client.
        """
        if self._file_chat_client is None and os.getenv("AZURE_OPENAI_ENDPOINT"):
            try:
                from azure_file_manager import AzureOpenAIChatWithFiles

                self._file_chat_client = AzureOpenAIChatWithFiles(
                    endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                    api_key=os.getenv("AZURE_OPENAI_KEY", ""),
                    deployment_id=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
                )
            except Exception as e:
                logger.error(f"Failed to initialize file chat client: {str(e)}")
        return self._file_chat_client

    def get_search_chat_client(self, model_type: str) -> Optional[Any]:
        """
        Get or create search chat client.
        """
        if self._search_chat_client is None and os.getenv("AZURE_SEARCH_ENDPOINT"):
            try:
                from azure_search_client import create_search_client

                self._search_chat_client = create_search_client(model_type)
            except Exception as e:
                logger.error(f"Failed to initialize search chat client: {str(e)}")
        return self._search_chat_client

    def validate_messages(self, messages: List[Message]) -> List[Message]:
        """
        Validate and sanitize chat messages.
        """
        if not isinstance(messages, list):
            raise ValueError("Messages must be a list")

        sanitized = []
        for msg in messages:
            if not isinstance(msg, dict):
                raise ValueError(f"Invalid message format: {msg}")
            if "role" not in msg or "content" not in msg:
                raise ValueError(f"Message missing required fields: {msg}")
            if msg["role"] not in ["system", "user", "assistant"]:
                raise ValueError(f"Invalid message role: {msg['role']}")
            if not isinstance(msg["content"], str):
                raise ValueError(f"Message content must be string: {msg}")

            content = msg["content"].strip()
            if content:
                sanitized.append({"role": msg["role"], "content": content})

        if not sanitized:
            raise ValueError("No valid messages provided")
        return sanitized

    def handle_stream_response(
        self, stream_response, model: str
    ) -> Generator[ChatResponse, None, None]:
        """
        Process streaming response from API.
        """
        current_content = ""
        consecutive_errors = 0
        MAX_RETRIES = 3

        try:
            for chunk in stream_response:
                try:
                    if not hasattr(chunk.choices[0], "delta"):
                        continue

                    delta = chunk.choices[0].delta
                    consecutive_errors = 0

                    if hasattr(delta, "role") and delta.role == "system":
                        continue

                    if hasattr(delta, "content") and delta.content:
                        current_content += delta.content
                        yield self._create_response(
                            delta.content, model, current_content
                        )

                    if chunk.choices[0].finish_reason:
                        yield self._create_response(
                            current_content,
                            model,
                            current_content,
                            chunk.choices[0].finish_reason,
                        )

                except Exception as e:
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_RETRIES:
                        raise Exception(f"Too many consecutive errors: {str(e)}")
        except Exception as e:
            yield self._create_error_response(str(e), model)

    def _create_response(
        self,
        content: str,
        model: str,
        full_content: str = "",
        finish_reason: Optional[str] = None,
    ) -> ChatResponse:
        """
        Create a standardized chat response.
        """
        return {
            "choices": [
                {
                    "message": {"content": content, "role": "assistant"},
                    "finish_reason": finish_reason,
                    "index": 0,
                }
            ],
            "created": int(datetime.now().timestamp()),
            "model": model,
        }

    def _create_error_response(self, error_message: str, model: str) -> ChatResponse:
        """
        Create a standardized error response.
        """
        return {
            "error": error_message,
            "choices": [
                {
                    "message": {
                        "content": f"An error occurred: {error_message}",
                        "role": "assistant",
                    },
                    "finish_reason": "error",
                    "index": 0,
                }
            ],
            "created": int(datetime.now().timestamp()),
            "model": model,
        }


_chat_client = ChatClient()


def get_azure_response(
    messages: List[Message],
    deployment_name: Optional[str] = None,
    max_completion_tokens: Optional[int] = None,
    api_endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: Optional[str] = None,
    model_type: Optional[str] = None,
    requires_o1_handling: bool = False,
    reasoning_effort: str = "medium",
    store_completion: bool = False,
    response_format: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 600,
    stream: bool = False,
    file_ids: Optional[List[str]] = None,
    vector_store_id: Optional[str] = None,
    use_code_interpreter: bool = False,
) -> ResponseType:
    """
    Get response from Azure OpenAI API.
    """
    try:
        required_params = {
            "deployment_name": deployment_name,
            "api_endpoint": api_endpoint,
            "api_key": api_key,
            "api_version": api_version,
        }
        missing = [k for k, v in required_params.items() if not v]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        if api_key:
            # Recreate the encryption key (same as used in create_default_model)
            config_instance = Config()  # create a Config instance
            key_bytes = hashlib.sha256(config_instance.ENCRYPTION_KEY.encode()).digest()
            encryption_key = base64.b64encode(key_bytes).decode()
            # Decrypt the stored API key
            logger.debug(f"Decrypted API key length: {len(api_key)}")
            api_key = decrypt_api_key(api_key, encryption_key)

        client = _chat_client.get_azure_client(api_key, api_endpoint, api_version)
        # Assuming Model.PROVIDER_CAPABILITIES is available via your model import.
        from models.model import Model

        model_caps = Model.PROVIDER_CAPABILITIES.get(model_type, {})
        sanitized_messages = _chat_client.validate_messages(messages)

        completion_params = {
            "model": deployment_name,
            "messages": sanitized_messages,
            "stream": stream,
            "temperature": 1.0 if model_caps.get("fixed_temperature") else 0.7,
            "max_tokens": min(
                max_completion_tokens or model_caps.get("max_tokens", 16384),
                model_caps.get("max_tokens", 16384),
            ),
        }

        if model_caps.get("requires_reasoning_effort"):
            completion_params.update(
                {
                    "reasoning_effort": reasoning_effort,
                    "store_completion": store_completion,
                }
            )

        if model_caps.get("supports_json_mode") and response_format:
            completion_params["response_format"] = response_format

        if stream and not model_caps.get("streaming", True):
            logger.warning(f"Streaming not supported for model type {model_type}")
            stream = False
            completion_params["stream"] = False

        response = client.chat.completions.create(**completion_params)

        if stream:
            return _chat_client.handle_stream_response(response, deployment_name)

        if not response or not response.choices:
            raise ValueError("Empty response from API")

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Error in get_azure_response: {str(e)}")
        raise


def upload_file_to_azure(
    file_content: bytes, file_name: str, content_type: str
) -> Optional[str]:
    """
    Upload file to Azure Blob Storage.
    """
    try:
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        container_name = os.getenv("AZURE_STORAGE_CONTAINER")

        if not connection_string or not container_name:
            logger.error("Azure Storage configuration missing")
            return None

        from azure.storage.blob import BlobServiceClient

        blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )
        container_client = blob_service_client.get_container_client(container_name)
        blob_name = f"{uuid.uuid4()}-{file_name}"
        blob_client = container_client.get_blob_client(blob_name)

        blob_client.upload_blob(
            file_content,
            blob_type="BlockBlob",
            content_settings={"content_type": content_type},
        )

        logger.info(f"Successfully uploaded file {file_name}")
        return blob_name

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        return None

def scrape_data(query: str) -> str:
    """
    Scrape data from external resources based on the provided query.

    Args:
        query (str): The search query or URL to scrape data from

    Returns:
        str: The scraped content or search results

    Raises:
        ValueError: If the query is invalid or empty
        Exception: For other errors during scraping
    """
    try:
        if not query or not isinstance(query, str):
            raise ValueError("Invalid query provided")

        headers = {"User-Agent": _chat_client._user_agent}
        response = requests.get(query, headers=headers, timeout=30)
        response.raise_for_status()

        return response.text

    except requests.RequestException as e:
        logger.error(f"Error scraping data: {str(e)}")
        raise ValueError(f"Failed to fetch data: {str(e)}")

