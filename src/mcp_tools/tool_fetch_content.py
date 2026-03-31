"""
MCP Tool 2 – fetch_search_content
==================================
Perform a Google Custom Search and return the **scraped content** of the
first *N* result links (default: 7).

Each link is fetched via the crawl4ai service and the markdown content is
returned.  Results are cached in Redis at two levels:

1. **Per-URL cache** – the crawled markdown for each individual URL is stored
   so that repeated visits to the same page within the TTL window are served
   from cache.
2. **Aggregate cache** – the full list of results for a given (query, max_links)
   pair is also cached so that an identical tool call can be served entirely
   from Redis.

Environment variables (see config.py)
--------------------------------------
GOOGLE_API_KEY / GOOGLE_CX / REDIS_* / CRAWL4AI_BASE_URL

Public interface
----------------
    results: list[dict] = await fetch_search_content(query, max_links=7)

Each element in *results* is a dict with the keys:
    url, title, description, keywords, author, content
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from src.mcp_tools.config import (
    GOOGLE_API_KEY,
    GOOGLE_CX,
    GOOGLE_API_MAX_RESULTS,
    GOOGLE_SEARCH_BASE_URL,
    MAX_SEARCH_RESULTS,
    MIN_CONTENT_LENGTH,
    REDIS_TTL,
)
from src.mcp_tools.crawl_client import crawl_urls
from src.mcp_tools.redis_cache import cache_get, cache_set, get_redis_client

logger = logging.getLogger(__name__)

_CACHE_NS_AGG = "mcp:fetch_search_content"
_CACHE_NS_URL = "mcp:url_content"

# Maximum number of links to visit (the tool parameter is capped at this value)
_HARD_LIMIT = 7


async def _google_search_links(
    session: aiohttp.ClientSession,
    query: str,
    num: int,
    lang: Optional[str],
    country: Optional[str],
) -> List[str]:
    """
    Return a list of result URLs from the Google Custom Search API.

    Filters out PDF links because those require a separate extraction path.
    """
    params: Dict[str, Any] = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX,
        "q": query,
        "num": max(1, min(num, GOOGLE_API_MAX_RESULTS)),
    }
    if lang:
        params["lr"] = lang
    if country:
        params["gl"] = country

    async with session.get(GOOGLE_SEARCH_BASE_URL, params=params) as response:
        if response.status != 200:
            body = await response.text()
            logger.error(
                "[fetch_search_content] Google API error status=%d body=%s",
                response.status,
                body[:500],
            )
            return []

        data = await response.json()

    total = int(data.get("searchInformation", {}).get("totalResults", 0))
    if total == 0:
        logger.warning("[fetch_search_content] Google returned 0 results for %r", query)
        return []

    links = [
        item["link"]
        for item in data.get("items", [])
        if not item["link"].lower().endswith(".pdf")
    ]
    logger.debug("[fetch_search_content] %d link(s) from Google", len(links))
    return links


async def fetch_search_content(
    query: str,
    max_links: int = _HARD_LIMIT,
    lang: Optional[str] = None,
    country: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search Google and return the scraped content of the top result pages.

    Parameters
    ----------
    query:
        Free-text search query.
    max_links:
        Maximum number of result pages to scrape.  Capped at 7.
    lang:
        Optional Google language restrict, e.g. ``"lang_de"``.
    country:
        Optional ISO 3166-1 alpha-2 country code for geolocation bias.

    Returns
    -------
    list[dict]
        One dict per successfully scraped URL with keys:
        ``url``, ``title``, ``description``, ``keywords``, ``author``,
        ``content``.
    """
    if not GOOGLE_API_KEY or not GOOGLE_CX:
        logger.error("[fetch_search_content] Missing GOOGLE_API_KEY or GOOGLE_CX")
        return []

    max_links = max(1, min(max_links, _HARD_LIMIT))

    # ------------------------------------------------------------------
    # Aggregate cache lookup
    # ------------------------------------------------------------------
    agg_key_raw = f"{_CACHE_NS_AGG}:{query}:{max_links}:{lang}:{country}"
    agg_cache_key = hashlib.sha256(agg_key_raw.encode()).hexdigest()

    redis = await get_redis_client()
    cached_agg = await cache_get(redis, agg_cache_key)
    if cached_agg:
        logger.debug("[fetch_search_content] Aggregate cache HIT for query=%r", query)
        return json.loads(cached_agg)

    # ------------------------------------------------------------------
    # Fetch link list from Google
    # ------------------------------------------------------------------
    # Request more results than needed to have spares after filtering
    google_num = min(max_links + 3, MAX_SEARCH_RESULTS)

    async with aiohttp.ClientSession() as session:
        all_links = await _google_search_links(session, query, google_num, lang, country)

    if not all_links:
        return []

    candidate_links = all_links[:max_links]

    # ------------------------------------------------------------------
    # Per-URL cache lookup
    # ------------------------------------------------------------------
    cached_results: List[Dict[str, Any]] = []
    urls_to_crawl: List[str] = []

    for url in candidate_links:
        url_key = hashlib.sha256(f"{_CACHE_NS_URL}:{url}".encode()).hexdigest()
        cached_url = await cache_get(redis, url_key)
        if cached_url:
            logger.debug("[fetch_search_content] URL cache HIT url=%s", url)
            cached_results.append(json.loads(cached_url))
        else:
            urls_to_crawl.append(url)

    # ------------------------------------------------------------------
    # Crawl uncached URLs
    # ------------------------------------------------------------------
    fresh_results: List[Dict[str, Any]] = []
    if urls_to_crawl:
        fresh_results = await crawl_urls(urls_to_crawl)

        # Cache each freshly crawled result individually
        for result in fresh_results:
            if result.get("content") and len(result["content"]) >= MIN_CONTENT_LENGTH:
                url_key = hashlib.sha256(
                    f"{_CACHE_NS_URL}:{result['url']}".encode()
                ).hexdigest()
                await cache_set(redis, url_key, json.dumps(result), ttl=REDIS_TTL)

    # ------------------------------------------------------------------
    # Merge and order results to match the original link order
    # ------------------------------------------------------------------
    result_map: Dict[str, Dict[str, Any]] = {
        r["url"]: r for r in (cached_results + fresh_results)
    }

    # Preserve the original Google ranking order
    ordered_results = [
        result_map[url] for url in candidate_links if url in result_map
    ]

    # ------------------------------------------------------------------
    # Aggregate cache store
    # ------------------------------------------------------------------
    if ordered_results:
        await cache_set(
            redis, agg_cache_key, json.dumps(ordered_results), ttl=REDIS_TTL
        )

    logger.info(
        "[fetch_search_content] query=%r → %d result(s) returned",
        query,
        len(ordered_results),
    )
    return ordered_results
