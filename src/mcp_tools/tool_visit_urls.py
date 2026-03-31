"""
MCP Tool 3 – visit_urls
========================
Given a list of URLs, fetch and return their scraped content via the
crawl4ai service.

Each URL is looked up in Redis first.  Only URLs that are not in the cache
are sent to crawl4ai; the fresh results are then stored back in Redis for
subsequent calls.

Environment variables (see config.py)
--------------------------------------
REDIS_HOST / REDIS_PORT / REDIS_TTL / CRAWL4AI_BASE_URL

Public interface
----------------
    results: list[dict] = await visit_urls(urls)

Each element in *results* is a dict with the keys:
    url, title, description, keywords, author, content

URLs that could not be scraped (network error, empty response, etc.) are
omitted from the result list rather than returning a partial/error entry.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List

from src.mcp_tools.config import MIN_CONTENT_LENGTH, REDIS_TTL
from src.mcp_tools.crawl_client import crawl_urls
from src.mcp_tools.redis_cache import cache_get, cache_set, get_redis_client

logger = logging.getLogger(__name__)

_CACHE_NS = "mcp:url_content"


async def visit_urls(urls: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch and return the content of the given URLs.

    Parameters
    ----------
    urls:
        List of URLs to visit.  Duplicate entries are de-duplicated while
        preserving the first occurrence order.

    Returns
    -------
    list[dict]
        One dict per successfully scraped URL with keys:
        ``url``, ``title``, ``description``, ``keywords``, ``author``,
        ``content``.

        The order of the returned list follows the order of *urls*.
        URLs that could not be scraped are absent from the result.
    """
    if not urls:
        return []

    # De-duplicate while preserving order
    seen: set = set()
    deduped: List[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)

    redis = await get_redis_client()

    # ------------------------------------------------------------------
    # Per-URL cache lookup
    # ------------------------------------------------------------------
    cached_map: Dict[str, Dict[str, Any]] = {}
    urls_to_crawl: List[str] = []

    for url in deduped:
        cache_key = hashlib.sha256(f"{_CACHE_NS}:{url}".encode()).hexdigest()
        cached_value = await cache_get(redis, cache_key)
        if cached_value:
            logger.debug("[visit_urls] Cache HIT url=%s", url)
            cached_map[url] = json.loads(cached_value)
        else:
            urls_to_crawl.append(url)

    # ------------------------------------------------------------------
    # Crawl uncached URLs
    # ------------------------------------------------------------------
    fresh_map: Dict[str, Dict[str, Any]] = {}
    if urls_to_crawl:
        fresh_results = await crawl_urls(urls_to_crawl)
        for result in fresh_results:
            content = result.get("content", "")
            if content and len(content) >= MIN_CONTENT_LENGTH:
                fresh_map[result["url"]] = result
                # Store in cache
                cache_key = hashlib.sha256(
                    f"{_CACHE_NS}:{result['url']}".encode()
                ).hexdigest()
                await cache_set(redis, cache_key, json.dumps(result), ttl=REDIS_TTL)
            else:
                logger.warning(
                    "[visit_urls] Skipping url=%s – content too short (%d chars)",
                    result.get("url"),
                    len(content),
                )

    # ------------------------------------------------------------------
    # Merge and return in original order
    # ------------------------------------------------------------------
    combined_map = {**cached_map, **fresh_map}
    ordered = [combined_map[url] for url in deduped if url in combined_map]

    logger.info(
        "[visit_urls] Requested %d URL(s), returning %d result(s)",
        len(deduped),
        len(ordered),
    )
    return ordered
