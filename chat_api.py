"""Module for Azure OpenAI API interaction and chat handling."""

import os
from typing import Optional, List, Dict, Union, Generator, Any, Mapping
import requests
from openai import AzureOpenAI
from scraping.ethical_scraper import EthicalScraper
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import ChoiceDelta
from azure.identity import DefaultAzureCredential

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
        self, api_key: str, api_endpoint: str, api_version: str,
        use_azure_ad: bool = False
    ) -> AzureOpenAI:
        """Get or create an Azure OpenAI client."""
        if not api_endpoint or not api_version:
            raise ChatAPIError("Missing required API configuration", 400)
        if not api_key and not use_azure_ad:
            raise ChatAPIError("Either API key or Azure AD auth is required", 400)

        try:
            if not self._azure_client:
                client_kwargs: Dict[str, Any] = {
                    "azure_endpoint": api_endpoint,
                    "api_version": api_version,
                }

                if use_azure_ad:
                    credential = DefaultAzureCredential()
                    client_kwargs["azure_ad_token"] = credential.get_token(
                        "https://cognitiveservices.azure.com/.default"
                    ).token
                else:
                    client_kwargs["api_key"] = api_key

                self._azure_client = AzureOpenAI(**client_kwargs)
            return self._azure_client
        except Exception as e:
            raise ChatAPIError(f"Failed to create Azure client: {str(e)}", 500)

    @staticmethod
    def is_o_series_model(model_type: Optional[str]) -> bool:
        """Check if the model is an o-series model."""
        if not model_type:
            return False
        return model_type.lower() in ["o3-mini", "o1", "o1-mini", "o1-preview"]

    @staticmethod
    def get_max_completion_tokens_limit(model_type: str) -> int:
        """Get the max completion tokens limit for a model type."""
        limits = {
            "o3-mini": 75000,
            "o1": 100000,
            "o1-mini": 50000,
            "o1-preview": 32768
        }
        return limits.get(model_type.lower(), 32000)  # Default to 32k for safety

    @staticmethod
    def supports_streaming(model_type: Optional[str]) -> bool:
        """Check if the model supports streaming."""
        if not model_type:
            return False
        return model_type.lower() == "o3-mini"

    @staticmethod
    def add_markdown_developer_message(messages: List[Message], model_type: Optional[str]) -> List[Message]:
        """Add developer message for markdown formatting if using o-series model."""
        if ChatClient.is_o_series_model(model_type):
            return [{"role": "developer", "content": "Formatting re-enabled - please enclose code blocks with appropriate markdown tags."}] + messages
        return messages


def get_azure_response(
    messages: List[Message],
    deployment_name: str,
    max_completion_tokens: int,
    api_endpoint: str,
    api_key: str,
    api_version: str,
    model_type: Optional[str] = None,
    requires_o1_handling: bool = False,
    reasoning_effort: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 600,
    stream: bool = False,
    temperature: Optional[float] = None,
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
            
        # Add markdown formatting message for o-series models
        messages = ChatClient.add_markdown_developer_message(messages, model_type)

        # Validate streaming support
        if stream and model_type and not ChatClient.supports_streaming(model_type):
            raise ChatAPIError(f"Model {model_type} does not support streaming", 400)

        # Get token limit for model type
        token_limit = ChatClient.get_max_completion_tokens_limit(model_type) if model_type else max_completion_tokens

        # Validate system messages for o-series models
        if model_type and model_type.lower() in ["o1-mini", "o1-preview"]:
            system_messages = [m for m in messages if m["role"] == "system"]
            if system_messages:
                raise ChatAPIError(f"Model {model_type} does not support system messages", 400)

        # Decrypt API key if needed
        try:
            if api_key:
                encryption_key = os.getenv("ENCRYPTION_KEY", "")
                api_key = decrypt_api_key(api_key, encryption_key)
        except Exception as e:
            raise ChatAPIError(f"API key decryption failed: {str(e)}", 500)

        # Create client with Azure AD support
        chat_client = ChatClient()
        use_azure_ad = os.getenv("AZURE_USE_AD_AUTH", "").lower() == "true"
        client = chat_client.get_azure_client(
            api_key=api_key,
            api_endpoint=api_endpoint,
            api_version=api_version,
            use_azure_ad=use_azure_ad
        )

        # Prepare completion parameters
        completion_params: Dict[str, Any] = {
            "model": deployment_name,
            "messages": messages,
            "stream": stream,
        }

        # Add optional parameters if provided
        if response_format:
            if not isinstance(response_format, dict) or "type" not in response_format:
                raise ChatAPIError("Invalid response_format structure", 400)
            completion_params["response_format"] = response_format

        # Handle o-series model parameters
        if model_type and ChatClient.is_o_series_model(model_type):
            # Validate API version for o-series models
            model_type_lower = model_type.lower()
            if model_type_lower in ["o3-mini", "o1"]:
                valid_versions = ["2024-12-01-preview", "2025-01-01-preview"]
                if api_version not in valid_versions:
                    raise ChatAPIError(f"Model {model_type} requires API version {' or '.join(valid_versions)}", 400)
            else:  # o1-preview and o1-mini
                valid_versions = ["2024-09-01-preview", "2024-10-01-preview", "2024-12-01-preview"]
                if api_version not in valid_versions:
                    raise ChatAPIError(f"Model {model_type} requires API version {', '.join(valid_versions[:-1])} or {valid_versions[-1]}", 400)

            # Set max_completion_tokens
            completion_params["max_completion_tokens"] = min(max_completion_tokens, token_limit)
            
            # Validate reasoning_effort parameter
            valid_efforts = ["low", "medium", "high"]
            if reasoning_effort and reasoning_effort not in valid_efforts:
                raise ChatAPIError(f"Invalid reasoning_effort value. Must be one of: {', '.join(valid_efforts)}", 400)
            if reasoning_effort:
                completion_params["reasoning_effort"] = reasoning_effort
            
            # Set fixed temperature for o-series models
            completion_params["temperature"] = 1.0

            # Remove any typical generation parameters that might break O-series usage
            for param in ["top_p", "presence_penalty", "frequency_penalty", "logprobs", "top_logprobs", "logit_bias"]:
                if param in completion_params:
                    del completion_params[param]
        else:
            # For standard models, use max_tokens
            completion_params["max_tokens"] = max_completion_tokens
            if temperature is not None:
                completion_params["temperature"] = temperature

        try:
            # Make API call
            logger.info("Sending request to chat completions with parameters: %s", completion_params)
            response = client.chat.completions.create(**completion_params)
            logger.info("Received response from chat completions: %s", type(response))
            if response:
                logger.info("Response object is truthy. Stream mode? %s", stream)
            else:
                logger.warning("No response object returned from chat completions. Stream: %s", stream)

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
        scraper = EthicalScraper()
        if not scraper.validate_access(query):
            raise ChatAPIError("Scraping not allowed by policy", 403)
            
        return scraper.scrape(query)

    except requests.Timeout:
        raise ChatAPIError("Request timed out", 504)
    except requests.RequestException as e:
        raise ChatAPIError(f"Request failed: {str(e)}", 502)
    except Exception as e:
        raise ChatAPIError(f"Scraping error: {str(e)}", 500)
