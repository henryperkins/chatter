"""
chat_api.py

This module provides functions for interacting with the Azure OpenAI API,
including sending chat messages and getting responses, as well as web scraping.
"""

import logging
from typing import Optional, List, Dict
import requests
from bs4 import BeautifulSoup
from openai import OpenAIError

from azure_config import initialize_client_from_model
from models import Model

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
) -> str:
    """
    Sends a chat message to the Azure OpenAI API and returns the response.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys.
        deployment_name: The name of the deployment (model) to use. If not provided,
            the default deployment will be used.
        selected_model_id: The ID of the selected model (optional).
        max_completion_tokens: The maximum number of completion tokens to generate.
        api_endpoint: The Azure OpenAI endpoint URL (optional).
        api_key: The Azure OpenAI API key (optional).
        api_version: The Azure OpenAI API version (optional).
        requires_o1_handling: Whether to use o1-preview specific handling (optional).

    Returns:
        The response string from the Azure OpenAI API.

    Raises:
        ValueError: If the selected model is not found.
        OpenAIError: If there is an error during API communication.
        Exception: If any other error occurs.
    """
    try:
        # Initialize defaults
        api_params = {
            "messages": [],  # Will be populated based on model type
        }

        # Create model config from provided credentials or get from database
        model_config = {}
        if selected_model_id:
            model = Model.get_by_id(selected_model_id)
            if not model:
                raise ValueError("Selected model not found.")
            model_config = model.__dict__

        # Override with any provided credentials
        if api_endpoint:
            model_config["api_endpoint"] = api_endpoint
        if api_key:
            model_config["api_key"] = api_key
        if api_version:
            model_config["api_version"] = api_version
        if deployment_name:
            model_config["deployment_name"] = deployment_name
        model_config["requires_o1_handling"] = requires_o1_handling

        # Initialize client from model config
        (
            client,
            deployment_name,
            temperature,
            max_tokens,
            max_completion_tokens,
            requires_o1_handling,
        ) = initialize_client_from_model(model_config)

        # Update api_params with model/deployment info
        api_params["model"] = deployment_name
        if max_completion_tokens:
            api_params["max_completion_tokens"] = max_completion_tokens

        # Filter messages based on model requirements
        api_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if not requires_o1_handling or msg["role"] != "system"
        ]
        api_params["messages"] = api_messages

        # Set parameters based on model type
        if requires_o1_handling:
            # Required parameters for o1-preview
            api_params.update({
                "temperature": 1,  # Must be 1 for o1-preview
                "max_completion_tokens": max_completion_tokens or 8500,  # Use model config or default to 8500
                "stream": False  # Streaming not supported
            })
            # Ensure max_tokens is not present
            api_params.pop("max_tokens", None)
        else:
            # Parameters for other models
            if temperature is not None:
                api_params["temperature"] = temperature
            if max_tokens is not None:
                api_params["max_tokens"] = max_tokens

        # Log the final API parameters for debugging
        logger.debug("Final API parameters: %s", api_params)

        # Make the API call
        response = client.chat.completions.create(**api_params)

        # Log full response for debugging
        logger.debug("Raw API response: %s", response.model_dump_json())

        # Extract model response with enhanced error checking
        if not response.choices:
            logger.error("No choices in model response")
            raise ValueError("Model response contained no choices")
            
        if not response.choices[0].message:
            logger.error("No message in first choice")
            raise ValueError("Model response choice contained no message")
            
        model_response = response.choices[0].message.content
        if not model_response:
            logger.error("Empty content in model response")
            raise ValueError("Model returned empty response content")

        # Log successful response
        logger.info(
            "Response received from the model (length: %d): %s",
            len(model_response),
            model_response[:100] + "..." if len(model_response) > 100 else model_response
        )
        return model_response

    except OpenAIError as e:
        logger.error(
            "OpenAI API error with %s model: %s",
            "o1-preview" if requires_o1_handling else "standard",
            str(e)
        )
        raise
    except Exception as e:
        logger.error(
            "Error in get_azure_response (%s model): %s",
            "o1-preview" if requires_o1_handling else "standard",
            str(e)
        )
        raise


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
        response.raise_for_status()  # Raise an exception for bad status codes
    except requests.exceptions.RequestException as e:
        logger.error("Error during web request for weather: %s", str(e))
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
        logger.error("Error during web request for search: %s", str(e))
        return "Could not retrieve search results due to a network error."

    soup = BeautifulSoup(response.text, "html.parser")
    # This selector is Google-dependent and may vary over time.
    results = soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd")
    search_results = [result.text for result in results[:3]]

    return "Search results:\n" + "\n".join(search_results)
