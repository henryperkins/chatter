"""Module for Azure OpenAI API interaction and chat handling."""

import os
import requests
import uuid
import httpx
from typing import Optional, List, Dict, Union, Generator, Any
from openai import AzureOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import ChoiceDelta

from logging_config import get_logger
from utils.encryption import decrypt_api_key
from scraping.ethical_scraper import EthicalScraper

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

    def __init__(self) -> None:
        self._azure_client: Optional[AzureOpenAI] = None
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )

    def get_azure_client(
        self, api_key: str, api_endpoint: str, api_version: str
    ) -> AzureOpenAI:
        """
        Create or reuse an AzureOpenAI client (key-based auth).
        Raises ChatAPIError if creation fails or config is missing.
        """
        if not all([api_endpoint, api_version, api_key]):
            raise ChatAPIError("Missing required API configuration", 400)

        try:
            if not self._azure_client:
                logger.info(
                    "Creating AzureOpenAI client with endpoint=%s, version=%s",
                    api_endpoint,
                    api_version
                )
                # Add HTTP client with proxy configuration
                http_client = None
                if os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"):
                    http_client = httpx.Client(
                        proxies={
                            "http://": os.environ.get("HTTP_PROXY"),
                            "https://": os.environ.get("HTTPS_PROXY")
                        }
                    )

                self._azure_client = AzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=api_endpoint,
                    api_version=api_version,
                    http_client=http_client  # Pass configured client here
                )

            return self._azure_client
        except Exception as e:
            raise ChatAPIError(f"Failed to create Azure client: {str(e)}", 500)

    @staticmethod
    def is_o_series_model(model_type: Optional[str]) -> bool:
        """
        Check if the model is an o-series (reasoning) model.
        E.g. 'o3-mini', 'o1', 'o1-mini', 'o1-preview'.
        """
        if not model_type:
            return False
        return model_type.lower() in ["o3-mini", "o1", "o1-mini", "o1-preview"]

    @staticmethod
    def get_max_completion_tokens_limit(model_type: str) -> int:
        """
        Get the max completion tokens limit for a known o-series model.
        Returns a default of 32,000 if not recognized.
        """
        limits = {
            "o3-mini": 75000,
            "o1": 100000,
            "o1-mini": 65536,
            "o1-preview": 32768,
        }
        return limits.get(model_type.lower(), 32000)

    @staticmethod
    def supports_streaming(model_type: Optional[str]) -> bool:
        """
        Check if the specific model supports streaming responses.
        Currently only 'o3-mini' is known to support streaming.
        """
        if not model_type:
            return False
        return model_type.lower() == "o3-mini"

    @staticmethod
    def add_markdown_developer_message(messages: List[Dict[str, str]],
                                       model_type: Optional[str]) -> List[Dict[str, str]]:
        """
        Insert a 'developer' role message to re-enable Markdown formatting.
        Only does this for o-series models.
        """
        if ChatClient.is_o_series_model(model_type):
            return [{
                "role": "developer",
                "content": (
                    "Formatting re-enabled - please enclose code blocks "
                    "with appropriate markdown tags."
                )
            }] + messages
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
    Send a chat request to Azure OpenAI (key-based auth). Returns a ChatCompletion
    or a generator for streaming. Raises ChatAPIError on failures.
    """
    try:
        # Validate required parameters
        if not all([messages, deployment_name, api_endpoint, api_key, api_version]):
            raise ChatAPIError("Missing required parameters", 400)

        # Validate messages structure
        if not isinstance(messages, list) or not all(
            isinstance(m, dict) and "role" in m and "content" in m for m in messages
        ):
            raise ChatAPIError("Invalid messages format", 400)

        # Possibly insert developer message for o-series
        messages = ChatClient.add_markdown_developer_message(messages, model_type)

        # Validate streaming if the model can't handle it
        if stream and model_type and not ChatClient.supports_streaming(model_type):
            raise ChatAPIError(f"Model {model_type} does not support streaming", 400)

        # Block system messages for o1-mini or o1-preview
        if model_type and model_type.lower() in ["o1-mini", "o1-preview"]:
            for msg in messages:
                if msg.get("role") == "system":
                    raise ChatAPIError(
                        f"Model {model_type} does not allow system messages. Use developer role instead.",
                        400
                    )

        # Determine the limit for max_completion_tokens
        token_limit = (
            ChatClient.get_max_completion_tokens_limit(model_type)
            if model_type
            else max_completion_tokens
        )

        # Some o-series models forbid system messages
        if model_type and model_type.lower() in ["o1-mini", "o1-preview"]:
            system_messages = [m for m in messages if m["role"] == "system"]
            if system_messages:
                raise ChatAPIError(
                    f"Model {model_type} does not support system messages", 400
                )

        # Create/reuse the AzureOpenAI client
        chat_client = ChatClient()
        client = chat_client.get_azure_client(
            api_key=api_key,
            api_endpoint=api_endpoint,
            api_version=api_version
        )

        # Prepare the base params
        completion_params: Dict[str, Any] = {
            "model": deployment_name,
            "messages": messages,
            "stream": stream,
        }

        # Check (and apply) optional response_format
        if response_format:
            if not isinstance(response_format, dict) or "type" not in response_format:
                raise ChatAPIError("Invalid response_format structure", 400)
            completion_params["response_format"] = response_format

        # Handle o-series constraints vs. standard model constraints
        if model_type and ChatClient.is_o_series_model(model_type):
            #
            # The docs say: o-series must use `max_completion_tokens`.
            # 'temperature', 'top_p', etc. are unsupported.
            #
            # Also verify version compatibility:
            model_type_lower = model_type.lower()

            # For o3-mini or o1, valid API versions:
            if model_type_lower in ["o3-mini", "o1"]:
                valid_versions = ["2024-12-01-preview", "2025-01-01-preview"]
                if api_version not in valid_versions:
                    raise ChatAPIError(
                        f"Model {model_type} requires API version {' or '.join(valid_versions)}",
                        400
                    )
            else:  # o1-mini, o1-preview
                valid_versions = [
                    "2024-09-01-preview",
                    "2024-10-01-preview",
                    "2024-12-01-preview"
                ]
                if api_version not in valid_versions:
                    raise ChatAPIError(
                        f"Model {model_type} requires API version "
                        f"{', '.join(valid_versions[:-1])} or {valid_versions[-1]}",
                        400
                    )

            completion_params["max_completion_tokens"] = min(max_completion_tokens, token_limit)
            if model_type_lower == "o1":
                completion_params["reasoning_effort"] = reasoning_effort or "medium"

            # Reasoning effort is optional, but must be one of ['low','medium','high']
            valid_efforts = ["low", "medium", "high"]
            if reasoning_effort and reasoning_effort not in valid_efforts:
                raise ChatAPIError(
                    f"Invalid reasoning_effort value. Must be one of: {', '.join(valid_efforts)}",
                    400
                )
            if reasoning_effort:
                completion_params["reasoning_effort"] = reasoning_effort

            # Remove typical generation parameters that break reasoning models
            for param in [
                "temperature", "top_p", "presence_penalty",
                "frequency_penalty", "logprobs", "top_logprobs", "logit_bias"
            ]:
                completion_params.pop(param, None)

        else:
            # For standard/legacy models: use max_tokens
            completion_params["max_tokens"] = max_completion_tokens

            # If a temperature was passed in, use it
            if temperature is not None:
                completion_params["temperature"] = temperature

        # Send the request to Azure OpenAI
        logger.info("Sending request to AzureOpenAI with params: %s", completion_params)
        response = client.chat.completions.create(**completion_params)

        logger.info("Received response from AzureOpenAI: %s", type(response))
        if response:
            logger.debug("Response is non-null; streaming: %s", stream)
        else:
            logger.warning("No response returned (None). Stream? %s", stream)

        # Return streaming or normal response
        if stream:
            return handle_streaming_response(response)
        return handle_normal_response(response)

    except ChatAPIError:
        raise
    except Exception as e:
        raise ChatAPIError(f"Unexpected error: {str(e)}", 500)


def handle_streaming_response(
    response: Generator[ChatCompletionChunk, None, None]
) -> Generator[ChatCompletionChunk, None, None]:
    """
    Handle streaming response (generator) from Azure OpenAI.
    Yields ChatCompletionChunk objects safely, raising ChatAPIError on errors.
    """
    try:
        for chunk in response:
            if not isinstance(chunk, ChatCompletionChunk):
                continue
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue

            choice = chunk.choices[0]
            if not isinstance(choice, Choice) or not hasattr(choice, "delta"):
                continue

            delta = choice.delta
            if not isinstance(delta, ChoiceDelta):
                continue

            # Yield the chunk if valid
            yield chunk

    except Exception as e:
        raise ChatAPIError(f"Error processing stream: {str(e)}", 500)


def handle_normal_response(response: ChatCompletion) -> ChatCompletion:
    """
    Handle normal (non-streaming) response from Azure OpenAI,
    verifying it has valid structure and logging relevant metadata.
    """
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

        # Log usage / IDs if needed
        logger.debug("Response usage: %s", getattr(response, "usage", None))
        logger.debug(
            "Response ID: %s, Model: %s",
            getattr(response, "id", None),
            getattr(response, "model", None)
        )

        # Return the ChatCompletion directly
        return response

    except ChatAPIError:
        raise
    except Exception as e:
        raise ChatAPIError(f"Error processing response: {str(e)}", 500)


async def scrape_data(query: str) -> str:
    """
    Asynchronous scraping method for external resources.
    Relies on an 'EthicalScraper' to check allowed content.
    """
    if not query or not isinstance(query, str):
        raise ChatAPIError("Invalid query provided", 400)

    try:
        scraper = EthicalScraper()
        if not scraper.validate_access(query):
            raise ChatAPIError("Scraping not allowed by policy", 403)

        result = await scraper.scrape(query)
        return result["content"]  # or handle as appropriate

    except requests.Timeout:
        raise ChatAPIError("Request timed out", 504)
    except requests.RequestException as e:
        raise ChatAPIError(f"Request failed: {str(e)}", 502)
    except Exception as e:
        raise ChatAPIError(f"Unexpected scraping error: {str(e)}", 500)
