import re
import os
import logging
from typing import List
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL detection pattern
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

def detect_urls(text: str) -> List[str]:
    """
    Extract URLs from the given text using regex pattern matching.
    
    Args:
        text (str): Input text containing potential URLs
        
    Returns:
        List[str]: List of detected URLs
    """
    try:
        return re.findall(URL_PATTERN, text)
    except Exception as e:
        logger.error(f"Error detecting URLs: {str(e)}")
        return []

def scrape_url(url: str) -> str:
    """
    Fetch content from the given URL with domain validation and error handling.
    
    Args:
        url (str): URL to scrape
        
    Returns:
        str: Raw HTML content from the URL or empty string if failed
    """
    try:
        # Validate URL format
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logger.error(f"Invalid URL format: {url}")
            return ""

        # Check allowed domains if configured
        allowed_domains = os.getenv('ALLOWED_SCRAPE_DOMAINS', '').split(',')
        if allowed_domains and allowed_domains[0]:  # Check if list is not empty
            if parsed_url.netloc not in allowed_domains:
                logger.warning(f"Domain not in allowed list: {parsed_url.netloc}")
                return ""

        # Make HTTP request with timeout
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text

    except requests.RequestException as e:
        logger.error(f"Error scraping URL {url}: {str(e)}")
        return ""
    except Exception as e:
        logger.error(f"Unexpected error while scraping {url}: {str(e)}")
        return ""

def format_scraped_data(raw_html: str) -> str:
    """
    Parse raw HTML and extract clean text content.
    
    Args:
        raw_html (str): Raw HTML content
        
    Returns:
        str: Cleaned and formatted text content
    """
    try:
        if not raw_html:
            return ""

        # Create BeautifulSoup object with appropriate parser
        soup = BeautifulSoup(raw_html, 'html.parser')

        # Remove script and style elements
        for element in soup(['script', 'style', 'head', 'header', 'footer', 'nav']):
            element.decompose()

        # Get text content
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)

        return text

    except Exception as e:
        logger.error(f"Error formatting HTML content: {str(e)}")
        return ""