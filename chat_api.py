"""Module for Azure OpenAI API interaction and chat handling."""

import logging
import os
from typing import Optional, List, Dict, Union, Generator, Any
import requests
from openai import AzureOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion import Choice, ChatCompletionMessage
from openai.types.chat.chat_completion_chunk import ChoiceDelta

from logging_config import get_logger
from utils.encryption import decrypt_api_key

logger = get_logger("chat_api")

# Type aliases
ResponseType = Union[ChatCompletion, str, Generator[ChatCompletionChunk, None, None]]
Message = Dict[str, str]
ChatResponse = Dict[str, Any]


class ChatAPIError(Exception):
    """Base exception for chat API errors."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ChatClient:
    """Manages chat interactions with Azure OpenAI API."""

    def __init__(self):
        self._azure_client: Optional[AzureOpenAI] = None
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )

    def get_azure_client(
        self, api_key: str, api_endpoint: str, api_version: str
    ) -> AzureOpenAI:
        """Get or create an Azure OpenAI client."""
        if not api_key or not api_endpoint or not api_version:
            raise ChatAPIError("Missing required API configuration", 400)

        try:
            if not self._azure_client:
                self._azure_client = AzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=api_endpoint,
                    api_version=api_version,
                )
            return self._azure_client
        except Exception as e:
            raise ChatAPIError(f"Failed to create Azure client: {str(e)}", 500)


def get_azure_response(
    messages: List[Message],
    deployment_name: str,
    max_completion_tokens: int,
    api_endpoint: str,
    api_key: str,
    api_version: str,
    model_type: Optional[str] = None,
    requires_o1_handling: bool = False,
    reasoning_effort: str = "medium",
    store_completion: bool = False,
    response_format: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 600,
    stream: bool = False,
) -> ResponseType:
    """
    Get response from Azure OpenAI API.
    """
    try:
        # Validate required parameters
        if not all([messages, deployment_name, api_endpoint, api_key, api_version]):
            raise ChatAPIError("Missing required parameters", 400)

        # Validate messages format
        if not isinstance(messages, list) or not all(
            isinstance(m, dict) and "role" in m and "content" in m for m in messages
        ):
            raise ChatAPIError("Invalid messages format", 400)

        # Decrypt API key if needed
        try:
            if api_key:
                encryption_key = os.getenv("ENCRYPTION_KEY", "")
                api_key = decrypt_api_key(api_key, encryption_key)
        except Exception as e:
            raise ChatAPIError(f"API key decryption failed: {str(e)}", 500)

        # Create client
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=api_endpoint,
            api_version=api_version,
            timeout=timeout_seconds,
        )

        # Prepare completion parameters
        completion_params = {
            "model": deployment_name,
            "messages": messages,
            "max_tokens": max_completion_tokens,
            "stream": stream,
        }

        # Add optional parameters if provided
        if response_format:
            if not isinstance(response_format, dict) or "type" not in response_format:
                raise ChatAPIError("Invalid response_format structure", 400)
            completion_params["response_format"] = response_format

        if requires_o1_handling:
            completion_params.update(
                {
                    "reasoning_effort": reasoning_effort,
                    "store_completion": store_completion,
                }
            )

        try:
            # Make API call
            response = client.chat.completions.create(**completion_params)

            if stream:
                return handle_streaming_response(response)
            return handle_normal_response(response)

        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                raise ChatAPIError("Request timed out", 504)
            if "rate limit" in error_msg.lower():
                raise ChatAPIError("Rate limit exceeded", 429)
            raise ChatAPIError(f"API request failed: {error_msg}", 500)

    except ChatAPIError:
        raise
    except Exception as e:
        raise ChatAPIError(f"Unexpected error: {str(e)}", 500)


def handle_streaming_response(
    response: Generator[ChatCompletionChunk, None, None]
) -> Generator[ChatCompletionChunk, None, None]:
    """Handle streaming response from the API."""
    try:
        for chunk in response:
            if not isinstance(chunk, ChatCompletionChunk):
                continue

            # Validate chunk structure
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue

            choice = chunk.choices[0]
            if not isinstance(choice, Choice) or not hasattr(choice, "delta"):
                continue

            delta = choice.delta
            if not isinstance(delta, ChoiceDelta):
                continue

            yield chunk

    except Exception as e:
        raise ChatAPIError(f"Error processing stream: {str(e)}", 500)


def handle_normal_response(response: ChatCompletion) -> ChatCompletion:
    """Handle normal (non-streaming) response from the API."""
    try:
        if not isinstance(response, ChatCompletion):
            raise ChatAPIError("Invalid response type from API", 500)

        if not hasattr(response, "choices") or not response.choices:
            raise ChatAPIError("No choices in API response", 500)

        choice = response.choices[0]
        if not isinstance(choice, Choice):
            raise ChatAPIError("Invalid choice type in response", 500)

        message = choice.message
        if not isinstance(message, ChatCompletionMessage):
            raise ChatAPIError("Invalid message type in response", 500)

        return response

    except ChatAPIError:
        raise
    except Exception as e:
        raise ChatAPIError(f"Error processing response: {str(e)}", 500)


def scrape_data(query: str) -> str:
    """
    Scrape data from external resources based on the provided query.
    """
    if not query or not isinstance(query, str):
        raise ChatAPIError("Invalid query provided", 400)

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }

        response = requests.get(query, headers=headers, timeout=30, verify=True)

        response.raise_for_status()
        return response.text

    except requests.Timeout:
        raise ChatAPIError("Request timed out", 504)
    except requests.RequestException as e:
        raise ChatAPIError(f"Request failed: {str(e)}", 502)
    except Exception as e:
        raise ChatAPIError(f"Scraping error: {str(e)}", 500)
