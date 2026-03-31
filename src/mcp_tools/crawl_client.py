"""
Async crawl4ai API client for MCP tools.

Sends one or more URLs to the crawl4ai service running in the same Docker
Compose network and returns structured results with the scraped markdown
content of each page.

Usage
-----
    from src.mcp_tools.crawl_client import crawl_urls

    results = await crawl_urls(["https://example.com", "https://example.org"])
    for r in results:
        print(r["url"], r["content"])
"""

import copy
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from src.mcp_tools.config import CRAWL4AI_BASE_URL, CRAWL4AI_DEFAULT_PAYLOAD

logger = logging.getLogger(__name__)


def _build_payload(urls: List[str], extra: Optional[Dict[str, Any]] = None) -> dict:
    """
    Merge *urls* and any caller-supplied overrides into the default crawl4ai
    request payload.
    """
    payload = copy.deepcopy(CRAWL4AI_DEFAULT_PAYLOAD)
    payload["urls"] = urls
    payload["crawler_config"]["params"]["stream"] = False  # batch mode

    if extra:
        payload.update(extra)

    return payload


def _extract_result(result_data: dict) -> Dict[str, Any]:
    """
    Transform a single crawl4ai result dict into a clean, flat dict that is
    easy to consume by the MCP tool functions.
    """
    metadata = result_data.get("metadata") or {}
    raw_markdown = (result_data.get("markdown") or {}).get("raw_markdown", "")

    return {
        "url": result_data.get("url", ""),
        "title": metadata.get("title", ""),
        "description": metadata.get("description", ""),
        "keywords": metadata.get("keywords", ""),
        "author": metadata.get("author", ""),
        "content": raw_markdown,
        # cleaned_html is kept so that consumers can fall back to it when
        # the crawl4ai markdown extractor produces an empty string (e.g. for
        # JavaScript-heavy pages that the markdown renderer cannot parse).
        "cleaned_html": result_data.get("cleaned_html", ""),
    }


async def crawl_urls(
    urls: List[str],
    session: Optional[aiohttp.ClientSession] = None,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Scrape *urls* via the crawl4ai REST API.

    Parameters
    ----------
    urls:
        List of URLs to crawl.
    session:
        An existing ``aiohttp.ClientSession``.  If *None* a temporary session
        is created and closed after the request.
    extra_payload:
        Optional dict whose keys are merged (top-level) into the request
        payload, allowing callers to override crawl4ai settings.

    Returns
    -------
    A list of result dicts (see ``_extract_result`` for the schema).  Failed
    or empty responses result in an empty list.
    """
    if not urls:
        return []

    payload = _build_payload(urls, extra_payload)

    _own_session = session is None
    if _own_session:
        session = aiohttp.ClientSession()

    try:
        async with session.post(
            CRAWL4AI_BASE_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as response:
            if response.status != 200:
                body = await response.text()
                logger.error(
                    "[MCP-CRAWL] API returned status=%d, body=%s",
                    response.status,
                    body[:500],
                )
                return []

            response_data = await response.json()

            if response_data.get("success") is False:
                logger.error("[MCP-CRAWL] crawl4ai reported failure: %s", response_data)
                return []

            results_raw: List[dict] = response_data.get("results", [])
            results = [_extract_result(r) for r in results_raw]
            logger.debug("[MCP-CRAWL] Crawled %d URL(s) successfully", len(results))
            return results

    except Exception as exc:
        logger.error("[MCP-CRAWL] Exception while crawling: %s", exc)
        return []

    finally:
        if _own_session:
            await session.close()
