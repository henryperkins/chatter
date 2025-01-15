import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict

logger = logging.getLogger(__name__)

# Common headers for requests
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
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
    logger.debug(f"Request headers for {url}: {DEFAULT_HEADERS}")
    
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        logger.debug(f"Response status code for {url}: {response.status_code}")
        logger.debug(f"Response content snippet for {url}: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        logger.error("Error during web request for weather: %s", str(e))
        logger.debug(f"Failed URL: {url}")
        logger.debug(f"Request headers: {DEFAULT_HEADERS}")
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
    logger.debug(f"Request headers for {url}: {DEFAULT_HEADERS}")
    
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        logger.debug(f"Response status code for {url}: {response.status_code}")
        logger.debug(f"Response content snippet for {url}: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        logger.error("Error during web request for search: %s", str(e))
        logger.debug(f"Failed URL: {url}")
        logger.debug(f"Request headers: {DEFAULT_HEADERS}")
        return "Could not retrieve search results due to a network error."

    soup = BeautifulSoup(response.text, "html.parser")
    # This selector is Google-dependent and may vary over time.
    results = soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd")
    search_results = [result.text for result in results[:3]]

    return "Search results:\n" + "\n".join(search_results)