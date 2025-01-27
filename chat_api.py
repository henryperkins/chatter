"""
chat_api.py

This module provides functions for interacting with the Azure OpenAI API,
including sending chat messages and getting responses, as well as web scraping.
"""

import logging
import json
from typing import Optional, List, Dict, Union, Generator, Any
import requests
from bs4 import BeautifulSoup

# Type aliases for better readability
ResponseType = Union[Dict[str, Any], str, Generator[Dict[str, Any], None, None]]
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
    timeout_seconds: int = 600,
    stream: bool = False,  # Add this parameter
) -> Union[Dict[str, Any], str, Generator]:
    try:
        # Validate parameters
        if not deployment_name or not api_endpoint or not api_key or not api_version:
            raise ValueError("Missing required parameters")

        # Ensure api_endpoint ends with '/'
        if not api_endpoint.endswith('/'):
            api_endpoint += '/'

        # Construct the endpoint URL including api_version
        endpoint = (
            f"{api_endpoint}openai/deployments/{deployment_name}/chat/completions"
            f"?api-version={api_version}"
        )
        headers = {
            "Content-Type": "application/json",
            "api-key": api_key,
        }

        # Prepare the payload
        payload = {
            "messages": messages,
            "temperature": 1.0,  # o1-preview models require temperature to be fixed at 1
            "max_tokens": max_completion_tokens or 256,
            "stream": stream,  # Add stream parameter
        }

        logger.debug("Making API call to %s with parameters: %s", endpoint, payload)

        # Make the API call using requests
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
            stream=stream,  # Enable streaming if requested
        )

        try:
            # Check for HTTP errors
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            logger.error("HTTP error occurred: %s", str(http_err))
            logger.error("Response content: %s", response.text)
            raise Exception(f"HTTP error occurred: {response.text}")
        except Exception as err:
            logger.error("Error occurred during API request: %s", str(err))
            raise Exception(f"Error occurred during API request: {str(err)}")

        if stream:
            # Return a generator that yields the response chunks
            def generate():
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8').strip()
                        if decoded_line == "":
                            continue
                        if decoded_line.startswith('data:'):
                            data_str = decoded_line[len('data:'):].strip()
                        else:
                            data_str = decoded_line
                        if data_str == '[DONE]':
                            break
                        else:
                            try:
                                data = json.loads(data_str)
                                yield data
                            except json.JSONDecodeError:
                                logger.error("Failed to parse JSON: %s", data_str)
                                continue
            return generate()
        else:
            # Handle non-streaming response
            json_response = response.json()
            if not json_response.get("choices"):
                logger.error("API returned unexpected response: %s", json_response)
                raise ValueError("API returned no choices")

            # Extract content
            choice = json_response["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"]
            elif "text" in choice:
                content = choice["text"]
            else:
                logger.error("API response format is unexpected: %s", json_response)
                raise ValueError("API response in unexpected format: no 'message' or 'text' field")

            if not content:
                raise ValueError("API returned empty content")

            logger.debug("Received response: %s", content[:100])
            return content


    except Exception as e:
        logger.error("Unexpected error: %s", str(e))
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
