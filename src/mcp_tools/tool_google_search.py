"""
MCP Tool 1 – google_search
==========================
Perform a Google Custom Search and return the **raw JSON response** from the
Google Custom Search API.

The Google Programmable Search Engine (PSE) must be configured with
"Search the entire web" enabled in the Google PSE control panel so that
results are not restricted to a specific domain.

Environment variables (see config.py)
--------------------------------------
GOOGLE_API_KEY  – Google Cloud API key with Custom Search enabled.
GOOGLE_CX       – Search Engine ID (cx) from the PSE control panel.
REDIS_HOST / REDIS_PORT / REDIS_TTL – Redis connection settings.

Public interface
----------------
    result: dict = await google_search(query, num=10, lang=None, country=None)

The returned dict is the unmodified JSON object returned by the Google API,
so callers receive the full ``searchInformation``, ``items``, ``queries``,
etc. structures.  On error an ``{"error": "…"}`` dict is returned.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from src.mcp_tools.config import (
    GOOGLE_API_KEY,
    GOOGLE_CX,
    GOOGLE_API_MAX_RESULTS,
    GOOGLE_SEARCH_BASE_URL,
    MAX_SEARCH_RESULTS,
    REDIS_TTL,
)
from src.mcp_tools.redis_cache import cache_get, cache_set, get_redis_client

logger = logging.getLogger(__name__)

# Cache namespace
_CACHE_NS = "mcp:google_search"


async def google_search(
    query: str,
    num: int = MAX_SEARCH_RESULTS,
    lang: Optional[str] = None,
    country: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform a Google Custom Search and return the raw JSON response.

    Parameters
    ----------
    query:
        Free-text search query.  No manual URL-encoding required.
    num:
        Number of results to return (capped at 10 by the Google API).
    lang:
        Optional language restrict, e.g. ``"lang_de"`` (German only).
        Omit to search all languages (entire web).
    country:
        Optional ISO 3166-1 alpha-2 country code to bias results geographically,
        e.g. ``"de"``.  Omit to search worldwide.

    Returns
    -------
    dict
        The unmodified JSON object returned by the Google Custom Search API,
        or ``{"error": "<message>"}`` on failure.
    """
    if not GOOGLE_API_KEY or not GOOGLE_CX:
        return {"error": "GOOGLE_API_KEY and GOOGLE_CX must be set."}

    # ------------------------------------------------------------------
    # Cache lookup
    # ------------------------------------------------------------------
    cache_key_raw = f"{_CACHE_NS}:{query}:{num}:{lang}:{country}"
    cache_key = hashlib.sha256(cache_key_raw.encode()).hexdigest()

    redis = await get_redis_client()
    cached = await cache_get(redis, cache_key)
    if cached:
        logger.debug("[google_search] Cache HIT for query=%r", query)
        return json.loads(cached)

    logger.debug("[google_search] Cache MISS – querying Google for query=%r", query)

    # ------------------------------------------------------------------
    # Live search
    # ------------------------------------------------------------------
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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(GOOGLE_SEARCH_BASE_URL, params=params) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.error(
                        "[google_search] API error status=%d body=%s",
                        response.status,
                        body[:500],
                    )
                    return {"error": f"Google API returned status {response.status}"}

                data: Dict[str, Any] = await response.json()

    except Exception as exc:
        logger.exception("[google_search] Request failed: %s", exc)
        return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Cache store
    # ------------------------------------------------------------------
    await cache_set(redis, cache_key, json.dumps(data), ttl=REDIS_TTL)
    logger.info(
        "[google_search] query=%r returned %d item(s)",
        query,
        len(data.get("items", [])),
    )
    return data
