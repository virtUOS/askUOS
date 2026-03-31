"""
Shared configuration for the MCP web-search tools.

All values are read from environment variables so that secrets are never
hard-coded in source code.  Set the variables below before starting the
MCP server (e.g. via a .env file or docker-compose environment section).

Required variables
------------------
GOOGLE_API_KEY  – Google Custom Search API key.
GOOGLE_CX       – Google Programmable Search Engine ID.
                  Configure the engine in the Google PSE control panel with
                  "Search the entire web" enabled so that results are not
                  restricted to a specific site.

Optional variables
------------------
REDIS_HOST          – Redis hostname.  Default: "redis"
REDIS_PORT          – Redis port.     Default: 6379
REDIS_TTL           – Cache TTL in seconds.  Default: 3600 (1 hour)
CRAWL4AI_BASE_URL   – Base URL of the crawl4ai service.
                      Default: "http://crawl4ai:11235/crawl"
MAX_SEARCH_RESULTS  – How many links the Google API should return (1-10).
                      Default: 10
"""

import os

# ---------------------------------------------------------------------------
# Google Custom Search
# ---------------------------------------------------------------------------
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CX: str = os.environ.get("GOOGLE_CX", "")

# Base endpoint – query params are appended at call time
GOOGLE_SEARCH_BASE_URL: str = "https://www.googleapis.com/customsearch/v1"

# Number of results the API should return (max allowed by Google: 10)
MAX_SEARCH_RESULTS: int = int(os.environ.get("MAX_SEARCH_RESULTS", "10"))

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
REDIS_HOST: str = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
# Default TTL: 1 hour
REDIS_TTL: int = int(os.environ.get("REDIS_TTL", "3600"))

# ---------------------------------------------------------------------------
# crawl4ai
# ---------------------------------------------------------------------------
CRAWL4AI_BASE_URL: str = os.environ.get(
    "CRAWL4AI_BASE_URL", "http://crawl4ai:11235/crawl"
)

# Default crawl4ai request payload (mirrors the structure expected by the API)
# Google Custom Search hard limit for results per request
GOOGLE_API_MAX_RESULTS: int = 10

# Minimum scraped content length (chars) to consider a result useful
MIN_CONTENT_LENGTH: int = 70

CRAWL4AI_DEFAULT_PAYLOAD: dict = {
    "crawler_config": {
        "type": "CrawlerRunConfig",
        "params": {
            "cache_mode": "BYPASS",
            "stream": False,
        },
    }
}
