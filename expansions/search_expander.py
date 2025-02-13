import logging
import os
import requests

logger = logging.getLogger(__name__)

class SearchExpander:
    """
    Simple gateway to external search APIs (like Tavily, Google CSE, SerpAPI).
    Merges expansions into conversation analysis.
    """
    def __init__(self):
        self.apis_enabled = ["tavily"]  # For example, we can add more: ["google", "serpapi"]
        self.api_key = os.getenv("TAVILY_API_KEY", "")
        self.base_url = "https://api.tavily.com"  # or other search providers

    def expand(self, text: str) -> str:
        """
        Query external APIs if text is flagged for expansion.
        Return additional context or empty string if no expansions found.
        """
        if not self.api_key or not self.apis_enabled:
            logger.debug("Search expansions not configured or disabled.")
            return ""

        # Example: call Tavily to get expansions
        try:
            payload = {"query": text, "max_results": 3}
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = requests.post(f"{self.base_url}/expand", json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Suppose data["expansions"] is a list of strings
            expansions = data.get("expansions", [])
            return "\n\n".join(expansions) if expansions else ""
        except Exception as e:
            logger.error("Expansion API call failed: %s", str(e))
            return ""
