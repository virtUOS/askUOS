import asyncio
import sys
import time
import warnings
from collections.abc import AsyncGenerator
from typing import AsyncGenerator, List, Optional, TypeVar, Union

import aiohttp
from colorama import Fore
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai.async_crawler_strategy import AsyncCrawlResponse
from crawl4ai.async_database import async_db_manager
from crawl4ai.async_dispatcher import *  # noqa: F403
from crawl4ai.cache_context import CacheContext, CacheMode, _legacy_to_cache_mode
from crawl4ai.chunking_strategy import *  # noqa: F403
from crawl4ai.chunking_strategy import ChunkingStrategy, IdentityChunking, RegexChunking
from crawl4ai.config import MIN_WORD_THRESHOLD
from crawl4ai.content_filter_strategy import *  # noqa: F403
from crawl4ai.content_filter_strategy import RelevantContentFilter
from crawl4ai.extraction_strategy import *  # noqa: F403
from crawl4ai.extraction_strategy import ExtractionStrategy, NoExtractionStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.models import CrawlResult
from crawl4ai.utils import create_box_message, get_error_context, sanitize_input_encode

# /root/.crawl4ai/crawl4ai.db   vs code  `code /root/.crawl4ai/`

# This code overrides the arun method of the AsyncWebCrawler class

CrawlResultT = TypeVar("CrawlResultT", bound=CrawlResult)
RunManyReturn = Union[List[CrawlResultT], AsyncGenerator[CrawlResultT, None]]

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator


class AsyncOverrideCrawler(AsyncWebCrawler):

    def __init__(self, **data):
        super().__init__(**data)

    async def delete_cached_result(self, db, sql_query):
        await db.execute(sql_query)

    async def arun(
        self,
        url: str,
        config: Optional[CrawlerRunConfig] = None,
        # Legacy parameters maintained for backwards compatibility
        word_count_threshold=MIN_WORD_THRESHOLD,
        extraction_strategy: ExtractionStrategy = None,
        chunking_strategy: ChunkingStrategy = RegexChunking(),
        content_filter: RelevantContentFilter = None,
        cache_mode: Optional[CacheMode] = None,
        # Deprecated cache parameters
        bypass_cache: bool = False,
        disable_cache: bool = False,
        no_cache_read: bool = False,
        no_cache_write: bool = False,
        # Other legacy parameters
        css_selector: str = None,
        screenshot: bool = False,
        pdf: bool = False,
        user_agent: str = None,
        verbose=True,
        **kwargs,
    ) -> CrawlResult:
        """
        Runs the crawler for a single source: URL (web, local file, or raw HTML).

        Migration Guide:
        Old way (deprecated):
            result = await crawler.arun(
                url="https://example.com",
                word_count_threshold=200,
                screenshot=True,
                ...
            )

        New way (recommended):
            config = CrawlerRunConfig(
                word_count_threshold=200,
                screenshot=True,
                ...
            )
            result = await crawler.arun(url="https://example.com", crawler_config=config)

        Args:
            url: The URL to crawl (http://, https://, file://, or raw:)
            crawler_config: Configuration object controlling crawl behavior
            [other parameters maintained for backwards compatibility]

        Returns:
            CrawlResult: The result of crawling and processing
        """
        crawler_config = config
        if not isinstance(url, str) or not url:
            raise ValueError("Invalid URL, make sure the URL is a non-empty string")

        async with self._lock or self.nullcontext():
            try:
                # Handle configuration
                if crawler_config is not None:
                    # if any(param is not None for param in [
                    #     word_count_threshold, extraction_strategy, chunking_strategy,
                    #     content_filter, cache_mode, css_selector, screenshot, pdf
                    # ]):
                    #     self.logger.warning(
                    #         message="Both crawler_config and legacy parameters provided. crawler_config will take precedence.",
                    #         tag="WARNING"
                    #     )
                    config = crawler_config
                else:
                    # Merge all parameters into a single kwargs dict for config creation
                    config_kwargs = {
                        "word_count_threshold": word_count_threshold,
                        "extraction_strategy": extraction_strategy,
                        "chunking_strategy": chunking_strategy,
                        "content_filter": content_filter,
                        "cache_mode": cache_mode,
                        "bypass_cache": bypass_cache,
                        "disable_cache": disable_cache,
                        "no_cache_read": no_cache_read,
                        "no_cache_write": no_cache_write,
                        "css_selector": css_selector,
                        "screenshot": screenshot,
                        "pdf": pdf,
                        "verbose": verbose,
                        **kwargs,
                    }
                    config = CrawlerRunConfig.from_kwargs(config_kwargs)

                # Handle deprecated cache parameters
                if any([bypass_cache, disable_cache, no_cache_read, no_cache_write]):
                    if kwargs.get("warning", True):
                        warnings.warn(
                            "Cache control boolean flags are deprecated and will be removed in version 0.5.0. "
                            "Use 'cache_mode' parameter instead.",
                            DeprecationWarning,
                            stacklevel=2,
                        )

                    # Convert legacy parameters if cache_mode not provided
                    if config.cache_mode is None:
                        config.cache_mode = _legacy_to_cache_mode(
                            disable_cache=disable_cache,
                            bypass_cache=bypass_cache,
                            no_cache_read=no_cache_read,
                            no_cache_write=no_cache_write,
                        )

                # Default to ENABLED if no cache mode specified
                if config.cache_mode is None:
                    config.cache_mode = CacheMode.ENABLED

                # Create cache context
                cache_context = CacheContext(
                    url, config.cache_mode, self.always_bypass_cache
                )

                # Initialize processing variables
                async_response: AsyncCrawlResponse = None
                cached_result: CrawlResult = None
                content_changed = True
                html = None
                screenshot_data = None
                pdf_data = None
                extracted_content = None
                start_time = time.perf_counter()

                # Try to get cached result if appropriate
                if cache_context.should_read():
                    cached_result = await async_db_manager.aget_cached_url(url)
                    print()

                if cached_result:
                    # check if content change

                    etag = cached_result.response_headers.get("etag")
                    last_modified = cached_result.response_headers.get("last-modified")
                    headers = {}
                    if etag:
                        headers["If-None-Match"] = etag

                    if last_modified:
                        headers["If-Modified-Since"] = last_modified

                    if etag or last_modified:
                        # TODO Look for the request object in crawl_web line 108

                        async with aiohttp.ClientSession() as session:
                            async with session.head(cached_result.url) as response:
                                new_etag = response.headers.get("Etag")

                                if new_etag:
                                    if etag == new_etag:

                                        # Content has not changed, skip crawling
                                        content_changed = False
                                        html = sanitize_input_encode(cached_result.html)
                                        extracted_content = sanitize_input_encode(
                                            cached_result.extracted_content or ""
                                        )
                                        extracted_content = (
                                            None
                                            if not extracted_content
                                            or extracted_content == "[]"
                                            else extracted_content
                                        )
                                        # If screenshot is requested but its not in cache, then set cache_result to None
                                        screenshot_data = cached_result.screenshot
                                        pdf_data = cached_result.pdf
                                        if (
                                            config.screenshot
                                            and not screenshot
                                            or config.pdf
                                            and not pdf
                                        ):
                                            cached_result = None

                                        self.logger.url_status(
                                            url=cache_context.display_url,
                                            success=bool(html),
                                            timing=time.perf_counter() - start_time,
                                            tag="FETCH",
                                        )
                                    else:
                                        # Content has changed, proceed to crawl
                                        sql_query = f"DELETE FROM crawled_data WHERE url = '{url}'"
                                        await async_db_manager.execute_with_retry(
                                            self.delete_cached_result,
                                            sql_query,
                                        )
                                        cached_result = None
                                        print()

                # Fetch fresh content if needed
                if (not cached_result or not html) and content_changed:
                    t1 = time.perf_counter()

                    if user_agent:
                        self.crawler_strategy.update_user_agent(user_agent)

                    # Check robots.txt if enabled
                    if config and config.check_robots_txt:
                        if not await self.robots_parser.can_fetch(
                            url, self.browser_config.user_agent
                        ):
                            return CrawlResult(
                                url=url,
                                html="",
                                success=False,
                                status_code=403,
                                error_message="Access denied by robots.txt",
                                response_headers={
                                    "X-Robots-Status": "Blocked by robots.txt"
                                },
                            )

                    # Pass config to crawl method
                    async_response = await self.crawler_strategy.crawl(
                        url,
                        config=config,  # Pass the entire config object
                    )

                    html = sanitize_input_encode(async_response.html)
                    screenshot_data = async_response.screenshot
                    pdf_data = async_response.pdf_data

                    t2 = time.perf_counter()
                    self.logger.url_status(
                        url=cache_context.display_url,
                        success=bool(html),
                        timing=t2 - t1,
                        tag="FETCH",
                    )

                    # Process the HTML content
                    crawl_result: CrawlResult = await self.aprocess_html(
                        url=url,
                        html=html,
                        extracted_content=extracted_content,
                        config=config,  # Pass the config object instead of individual parameters
                        screenshot=screenshot_data,
                        pdf_data=pdf_data,
                        verbose=config.verbose,
                        is_raw_html=True if url.startswith("raw:") else False,
                        **kwargs,
                    )

                    crawl_result.status_code = async_response.status_code
                    crawl_result.redirected_url = async_response.redirected_url or url
                    crawl_result.response_headers = async_response.response_headers
                    crawl_result.downloaded_files = async_response.downloaded_files
                    crawl_result.ssl_certificate = (
                        async_response.ssl_certificate
                    )  # Add SSL certificate

                    crawl_result.success = bool(html)
                    crawl_result.session_id = getattr(config, "session_id", None)

                    self.logger.success(
                        message="{url:.50}... | Status: {status} | Total: {timing}",
                        tag="COMPLETE",
                        params={
                            "url": cache_context.display_url,
                            "status": crawl_result.success,
                            "timing": f"{time.perf_counter() - start_time:.2f}s",
                        },
                        colors={
                            "status": Fore.GREEN if crawl_result.success else Fore.RED,
                            "timing": Fore.YELLOW,
                        },
                    )

                    # Update cache if appropriate
                    if cache_context.should_write() and not bool(cached_result):
                        await async_db_manager.acache_url(crawl_result)

                    return crawl_result

                else:
                    self.logger.success(
                        message="{url:.50}... | Status: {status} | Total: {timing}",
                        tag="COMPLETE",
                        params={
                            "url": cache_context.display_url,
                            "status": True,
                            "timing": f"{time.perf_counter() - start_time:.2f}s",
                        },
                        colors={"status": Fore.GREEN, "timing": Fore.YELLOW},
                    )

                    cached_result.success = bool(html)
                    cached_result.session_id = getattr(config, "session_id", None)
                    cached_result.redirected_url = cached_result.redirected_url or url
                    return cached_result

            except Exception as e:
                error_context = get_error_context(sys.exc_info())

                error_message = (
                    f"Unexpected error in _crawl_web at line {error_context['line_no']} "
                    f"in {error_context['function']} ({error_context['filename']}):\n"
                    f"Error: {str(e)}\n\n"
                    f"Code context:\n{error_context['code_context']}"
                )

                self.logger.error_status(
                    url=url,
                    error=create_box_message(error_message, type="error"),
                    tag="ERROR",
                )

                return CrawlResult(
                    url=url, html="", success=False, error_message=error_message
                )


if __name__ == "__main__":
    # Example usage
    browser_config = BrowserConfig(
        headless=True,
        verbose=True,
    )
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.ENABLED,
        scan_full_page=True,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.48, threshold_type="fixed", min_word_threshold=0
            )
        ),
    )

    async def crawl():
        async with AsyncOverrideCrawler(config=browser_config) as crawler:

            # url = "https://zilliz.com/blog/sharding-partitioning-segments-get-most-from-your-database"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/masterstudiengaenge-zwei-faecher#c52103"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/bachelorstudiengaenge-zwei-faecher-zulassungsbeschraenkt"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/bachelorstudiengaenge-ein-fach-zulassungsfrei"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/masterstudiengaenge-zwei-faecher"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/masterstudiengaenge-ein-fach"
            url = "https://www.uni-osnabrueck.de/studieren/unsere-studienangebote/abschluesse-und-ordnungen/2-faecher-bachelor"

            result = await crawler.arun(url, config=run_config)
            print(result)

    asyncio.run(crawl())
    print()
