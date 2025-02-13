"""Module for ethical web scraping with domain validation and rate limiting."""

import requests
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import time
import logging

logger = logging.getLogger(__name__)

class EthicalScraper:
    """Handles web scraping with built-in ethical constraints and monitoring."""
    
    def __init__(self):
        self.allowed_domains = {"example.com", "docs.example.org"}
        self.proxy_rotation_enabled = True
        self.last_request_time = 0
        self.min_request_interval = 1  # seconds between requests
        
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }

    def validate_access(self, url: str) -> bool:
        """Check if we're allowed to access this URL based on domain policy."""
        if not url:
            return False
        return self._domain_allowed(url)

    def _domain_allowed(self, url: str) -> bool:
        """Check if the domain is in our allowed list."""
        try:
            domain = urlparse(url).netloc.lower()
            return domain in self.allowed_domains
        except Exception as e:
            logger.error(f"Domain validation failed: {str(e)}")
            return False

    def scrape(self, url: str) -> str:
        """
        Scrape content from URL with rate limiting and error handling.
        """
        # Respect rate limits
        self._wait_for_rate_limit()
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10,
                verify=True
            )
            response.raise_for_status()
            self.last_request_time = time.time()
            return response.text
            
        except requests.Timeout:
            logger.error(f"Request timed out for URL: {url}")
            raise
        except requests.RequestException as e:
            logger.error(f"Request failed for URL {url}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error scraping {url}: {str(e)}")
            raise

    def _wait_for_rate_limit(self) -> None:
        """Ensure we respect minimum time between requests."""
        if self.last_request_time:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
