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

from azure_config import get_azure_client, initialize_client_from_model
from models import Model

logger = logging.getLogger(__name__)


def get_azure_response(
    messages: List[Dict[str, str]],
    deployment_name: Optional[str] = None,
    selected_model_id: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
) -> str:
    """
    Sends a chat message to the Azure OpenAI API and returns the response.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys.
        deployment_name: The name of the deployment (model) to use. If not provided,
            the default deployment will be used.
        selected_model_id: The ID of the selected model (optional).
        max_completion_tokens: The maximum number of completion tokens to generate.

    Returns:
        The response string from the Azure OpenAI API.

    Raises:
        ValueError: If the selected model is not found.
        OpenAIError: If there is an error during API communication.
        Exception: If any other error occurs.
    """
    try:
        # Retrieve the cached client and deployment name
        client, deployment_name = get_azure_client(deployment_name)

        # Initialize defaults
        api_params = {
            "model": deployment_name,
            "messages": [],  # Will be populated based on model type
            "max_completion_tokens": max_completion_tokens or 500  # Default if not provided
        }

        # If a specific model is selected, fetch its info from the database
        if selected_model_id:
            model = Model.get_by_id(selected_model_id)
            if not model:
                raise ValueError("Selected model not found.")

            (
                client,
                deployment_name,
                temperature,
                max_tokens,
                max_completion_tokens,
                requires_o1_handling,
            ) = initialize_client_from_model(model.__dict__)

            # Update api_params with model-specific values
            api_params["model"] = deployment_name
            if max_completion_tokens:
                api_params["max_completion_tokens"] = max_completion_tokens
        else:
            # Default behavior without specific model
            requires_o1_handling = any(
                model_name in deployment_name
                for model_name in ['o1-preview']
            )
            temperature = 1 if requires_o1_handling else 0.7

        # Filter messages based on model requirements
        api_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if not requires_o1_handling or msg["role"] != "system"
        ]
        api_params["messages"] = api_messages

        # Set temperature and tokens based on model type
        if requires_o1_handling:
            api_params["temperature"] = 1  # Required for o1-preview
            # Remove max_tokens if present, use max_completion_tokens
            api_params.pop("max_tokens", None)
        else:
            if temperature is not None:
                api_params["temperature"] = temperature
            if max_tokens is not None:
                api_params["max_tokens"] = max_tokens

        # Make the API call (no streaming for o1-preview)
        response = client.chat.completions.create(
            **api_params,
            stream=False if requires_o1_handling else None
        )

        # Extract model response
        if response.choices and response.choices[0].message:
            model_response = response.choices[0].message.content
        else:
            model_response = (
                "The assistant was unable to generate a response. "
                "Please try again or rephrase your input."
            )

        logger.info("Response received from the model: %s", model_response)
        return model_response

    except OpenAIError as e:
        logger.error("OpenAI API error: %s", str(e))
        raise
    except Exception as e:
        logger.error("Error in get_azure_response: %s", str(e))
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
    weather_element = soup.find("div", class_="BNeawe")

    if weather_element:
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
