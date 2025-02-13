import unittest
from unittest.mock import patch, Mock
import requests_mock
from utils.web_scraper import detect_urls, scrape_url, format_scraped_data

class TestWebScraper(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.sample_urls = [
            "https://example.com",
            "http://test.org/page",
            "https://sub.domain.com/path?param=value"
        ]
        self.sample_html = """
        <html>
            <body>
                <h1>Test Title</h1>
                <p>This is a test paragraph.</p>
                <div class="content">
                    <p>More content here.</p>
                </div>
            </body>
        </html>
        """

    def test_detect_urls_single(self):
        """Test detection of a single URL in text."""
        text = "Check out this link: https://example.com"
        urls = detect_urls(text)
        self.assertEqual(urls, ["https://example.com"])

    def test_detect_urls_multiple(self):
        """Test detection of multiple URLs in text."""
        text = "Visit https://example.com and http://test.org/page"
        urls = detect_urls(text)
        self.assertEqual(urls, ["https://example.com", "http://test.org/page"])

    def test_detect_urls_no_urls(self):
        """Test behavior when no URLs are present."""
        text = "This text contains no URLs"
        urls = detect_urls(text)
        self.assertEqual(urls, [])

    def test_detect_urls_complex(self):
        """Test detection of URLs with query parameters and fragments."""
        text = "Complex URL: https://example.com/path?param=value#section"
        urls = detect_urls(text)
        self.assertEqual(urls, ["https://example.com/path?param=value#section"])

    @requests_mock.Mocker()
    def test_scrape_url_success(self, m):
        """Test successful URL scraping."""
        url = "https://example.com"
        m.get(url, text=self.sample_html)
        
        result = scrape_url(url)
        self.assertIsNotNone(result)
        self.assertEqual(result, self.sample_html)

    @requests_mock.Mocker()
    def test_scrape_url_timeout(self, m):
        """Test URL scraping with timeout."""
        url = "https://example.com"
        m.get(url, exc=requests.exceptions.Timeout)
        
        result = scrape_url(url)
        self.assertIsNone(result)

    @requests_mock.Mocker()
    def test_scrape_url_connection_error(self, m):
        """Test URL scraping with connection error."""
        url = "https://example.com"
        m.get(url, exc=requests.exceptions.ConnectionError)
        
        result = scrape_url(url)
        self.assertIsNone(result)

    def test_format_scraped_data_basic(self):
        """Test basic HTML formatting."""
        html = "<html><body><p>Test content</p></body></html>"
        formatted = format_scraped_data(html)
        self.assertEqual(formatted.strip(), "Test content")

    def test_format_scraped_data_complex(self):
        """Test formatting of complex HTML structure."""
        formatted = format_scraped_data(self.sample_html)
        expected_text = "Test Title\nThis is a test paragraph.\nMore content here."
        self.assertEqual(formatted.strip(), expected_text.strip())

    def test_format_scraped_data_empty(self):
        """Test formatting of empty HTML."""
        html = ""
        formatted = format_scraped_data(html)
        self.assertEqual(formatted.strip(), "")

    def test_format_scraped_data_invalid_html(self):
        """Test formatting of invalid HTML."""
        html = "<invalid><<html>>Test</invalid>"
        formatted = format_scraped_data(html)
        self.assertIsNotNone(formatted)
        self.assertTrue(len(formatted.strip()) > 0)

if __name__ == '__main__':
    unittest.main()