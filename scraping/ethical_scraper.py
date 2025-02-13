"""Module for ethical web scraping with domain validation and rate limiting."""

import requests
from typing import Optional, Dict, Any, Union, Tuple
from urllib.parse import urlparse
import time
import logging
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

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
        
        # Patterns that suggest JavaScript rendering is needed
        self.js_required_patterns = ["window.__INITIAL_STATE__", "window.__NUXT__", 
                                   "window.__NEXT_DATA__", '<div id="app"></div>', 
                                   '<div id="root"></div>']

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

    async def scrape(self, url: str) -> Dict[str, Any]:
        """
        Scrape content from URL with hybrid rendering detection.
        First tries simple request, falls back to Playwright if JS rendering needed.
        """
        # Respect rate limits
        self._wait_for_rate_limit()
        
        try:
            # First attempt: Simple request
            content, needs_js = await self._try_simple_request(url)
            
            # If content seems to need JS rendering, use Playwright
            if needs_js:
                logger.info(f"JS rendering required for {url}, using Playwright")
                content = await self._render_with_playwright(url)
            
            self.last_request_time = time.time()
            return {
                "content": content,
                "used_js_rendering": needs_js,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            raise

    async def _try_simple_request(self, url: str) -> tuple[str, bool]:
        """Attempt simple request and check if JS rendering is needed."""
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10,
                verify=True
            )
            response.raise_for_status()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if content likely needs JS rendering
            needs_js = any(pattern in response.text for pattern in self.js_required_patterns)
            
            # Additional checks for empty content
            main_content = soup.find(['article', 'main', '#content', '.content'])
            if main_content and not main_content.text.strip():
                needs_js = True
                
            return response.text, needs_js
            
        except Exception as e:
            logger.error(f"Simple request failed for {url}: {str(e)}")
            return "", True  # Assume JS needed if request fails

    async def _render_with_playwright(self, url: str) -> str:
        """Use Playwright for JavaScript rendering."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            
            try:
                await page.goto(url, wait_until="networkidle")
                content = await page.content()
                return content
            finally:
                await browser.close()

    def _wait_for_rate_limit(self) -> None:
        """Ensure we respect minimum time between requests."""
        if self.last_request_time:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
