"""
chat_api.py

This module provides functions for interacting with the Azure OpenAI API,
including sending chat messages and getting responses, as well as web scraping.
"""

import logging
from typing import Optional, List, Dict, Union, Generator, Any, cast
import requests
from bs4 import BeautifulSoup
from openai import OpenAIError, Client
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from azure_config import initialize_client_from_model
from models import Model

# Type aliases for better readability
ResponseType = Union[str, Generator[ChatCompletionChunk, None, None]]
ApiParams = Dict[str, Any]

logger = logging.getLogger(__name__)


def get_azure_response(
    messages: List[Dict[str, str]],
    deployment_name: Optional[str] = None,
    selected_model_id: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    api_endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: Optional[str] = None,
    requires_o1_handling: bool = False,
    stream: bool = False,
    timeout_seconds: int = 600,
) -> ResponseType:
    """
    Sends a chat message to the Azure OpenAI API and returns the response.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys.
        deployment_name: The name of the deployment (model) to use.
        selected_model_id: The ID of the selected model (optional).
        max_completion_tokens: The maximum number of completion tokens to generate.
        api_endpoint: The Azure OpenAI endpoint URL.
        api_key: The Azure OpenAI API key.
        api_version: The Azure OpenAI API version.
        requires_o1_handling: Whether to use o1-preview specific handling.
        stream: Whether to stream the response.
        timeout_seconds: Timeout for the API call.

    Returns:
        The response string or stream from the Azure OpenAI API.

    Raises:
        ValueError: If required parameters are missing or invalid.
        Exception: If any other error occurs.
    """
    try:
        # Validate required parameters
        if not deployment_name:
            raise ValueError("Deployment name is required")
        if not api_endpoint:
            raise ValueError("API endpoint is required")
        if not api_key:
            raise ValueError("API key is required")
        if not api_version:
            raise ValueError("API version is required")
        if not messages:
            raise ValueError("Messages are required")

        # Log configuration details
        logger.debug("Initializing Azure API client with config:", {
            "deployment_name": deployment_name,
            "api_endpoint": api_endpoint,
            "requires_o1_handling": requires_o1_handling,
            "stream": stream,
            "max_completion_tokens": max_completion_tokens
        })

        # Initialize client
        client = initialize_client_from_model({
            "deployment_name": deployment_name,
            "api_endpoint": api_endpoint,
            "api_key": api_key,
            "api_version": api_version,
            "requires_o1_handling": requires_o1_handling,
            "timeout_seconds": timeout_seconds
        })

        # Validate and prepare messages
        if not isinstance(messages, list):
            raise ValueError("Messages must be a list")
        
        validated_messages = []
        for msg in messages:
            if not isinstance(msg, dict):
                raise ValueError("Each message must be a dictionary")
            if "role" not in msg or "content" not in msg:
                raise ValueError("Each message must have 'role' and 'content' keys")
            validated_messages.append({
                "role": msg["role"],
                "content": str(msg["content"])
            })

        logger.debug("Sending validated messages:", validated_messages)

        # Prepare API parameters
        api_params = {
            "model": deployment_name,
            "messages": validated_messages,
            "temperature": 1.0 if requires_o1_handling else 0.7,
            "max_tokens": max_completion_tokens,
            "stream": stream and not requires_o1_handling
        }

        # Make API call
        logger.debug("Making API call with parameters:", api_params)
        response = client.chat.completions.create(**api_params)

        # Handle streaming response
        if stream:
            logger.debug("Returning streaming response")
            return response

        # Handle non-streaming response
        logger.debug("Received raw API response:", response)

        if not response.choices:
            logger.error("No choices in API response")
            raise ValueError("API returned no choices")
        
        if not response.choices[0].message:
            logger.error("No message in first choice")
            raise ValueError("API response choice contained no message")

        content = response.choices[0].message.content
        if not content:
            logger.error("Empty content in API response")
            raise ValueError("API returned empty content")

        logger.info("Response received from the model (length: %d): %s",
            len(content), content[:100] + "..." if len(content) > 100 else content)

        return content

    except ValueError as e:
        logger.error("Validation error in get_azure_response: %s", str(e))
        return {"error": f"Configuration error: {str(e)}"}
    except OpenAIError as e:
        logger.error("OpenAI API error: %s", str(e), exc_info=True)
        error_mapping = {
            "Invalid API key": "The provided API key is invalid. Please check your configuration.",
            "Model not found": "The selected model is not available. Please choose a different model.",
            "Rate limit exceeded": "The API rate limit has been exceeded. Please try again later.",
            "Invalid request": "The API request was invalid. Please check your configuration.",
            "AuthenticationError": "Authentication failed. Please check your API key and endpoint.",
            "APIConnectionError": "Could not connect to the API. Please check your network connection.",
            "APIError": "An unexpected API error occurred. Please try again later."
        }
        user_message = error_mapping.get(str(e), f"An API error occurred: {str(e)}")
        return {"error": user_message}
    except Exception as e:
        logger.error("Unexpected error in get_azure_response: %s", str(e), exc_info=True)
        return {
            "error": str(e),
            "details": {
                "deployment": deployment_name,
                "endpoint": api_endpoint,
                "version": api_version,
                "requires_o1_handling": requires_o1_handling,
                "stream": stream
            }
        }


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
    logger.debug(f"Request headers for {url}: {headers}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        logger.debug(f"Response status code for {url}: {response.status_code}")
        logger.debug(f"Response content snippet for {url}: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        logger.error("Error during web request for weather: %s", str(e))
        logger.debug(f"Failed URL: {url}")
        logger.debug(f"Request headers: {headers}")
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
    logger.debug(f"Request headers for {url}: {headers}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.debug(f"Response status code for {url}: {response.status_code}")
        logger.debug(f"Response content snippet for {url}: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        logger.error("Error during web request for search: %s", str(e))
        logger.debug(f"Failed URL: {url}")
        logger.debug(f"Request headers: {headers}")
        return "Could not retrieve search results due to a network error."

    soup = BeautifulSoup(response.text, "html.parser")
    # This selector is Google-dependent and may vary over time.
    results = soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd")
    search_results = [result.text for result in results[:3]]

    return "Search results:\n" + "\n".join(search_results)
