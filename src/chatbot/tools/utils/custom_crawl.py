import asyncio
import sys
import time

import aiohttp
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, ProxyConfig
from crawl4ai.async_crawler_strategy import AsyncCrawlResponse
from crawl4ai.async_database import async_db_manager
from crawl4ai.async_dispatcher import *  # noqa: F403
from crawl4ai.cache_context import CacheContext, CacheMode, _legacy_to_cache_mode
from crawl4ai.chunking_strategy import *  # noqa: F403
from crawl4ai.content_filter_strategy import *  # noqa: F403
from crawl4ai.extraction_strategy import *  # noqa: F403
from crawl4ai.models import CrawlResult, CrawlResultContainer, RunManyReturn
from crawl4ai.utils import create_box_message, get_error_context, sanitize_input_encode

# /root/.crawl4ai/crawl4ai.db   vs code  `code /root/.crawl4ai/`

# This code overrides the arun method of the AsyncWebCrawler class

# CrawlResultT = TypeVar("CrawlResultT", bound=CrawlResult)
# RunManyReturn = Union[List[CrawlResultT], AsyncGenerator[CrawlResultT, None]]


async def delete_cached_result(self, db, sql_query):
    await db.execute(sql_query)


async def arun(
    self,
    url: str,
    config: CrawlerRunConfig = None,
    **kwargs,
) -> RunManyReturn:
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
    # Auto-start if not ready
    if not self.ready:
        await self.start()

    config = config or CrawlerRunConfig()
    if not isinstance(url, str) or not url:
        raise ValueError("Invalid URL, make sure the URL is a non-empty string")

    async with self._lock or self.nullcontext():
        try:
            self.logger.verbose = config.verbose

            # Default to ENABLED if no cache mode specified
            if config.cache_mode is None:
                config.cache_mode = CacheMode.ENABLED

            # Create cache context
            cache_context = CacheContext(url, config.cache_mode, False)

            # Initialize processing variables
            async_response: AsyncCrawlResponse = None
            cached_result: CrawlResult = None
            html = None
            content_changed = True
            screenshot_data = None
            pdf_data = None
            extracted_content = None
            start_time = time.perf_counter()

            # Try to get cached result if appropriate
            if cache_context.should_read():
                cached_result = await async_db_manager.aget_cached_url(url)

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
                                    # if config.screenshot and not screenshot or config.pdf and not pdf:
                                    if config.screenshot and not screenshot_data:
                                        cached_result = None

                                    if config.pdf and not pdf_data:
                                        cached_result = None

                                    self.logger.url_status(
                                        url=cache_context.display_url,
                                        success=bool(html),
                                        timing=time.perf_counter() - start_time,
                                        tag="FETCH",
                                    )
                                else:
                                    # Content has changed, proceed to crawl
                                    sql_query = (
                                        f"DELETE FROM crawled_data WHERE url = '{url}'"
                                    )
                                    await async_db_manager.execute_with_retry(
                                        self.delete_cached_result,
                                        sql_query,
                                    )
                                    cached_result = None
                                    print()

            # Update proxy configuration from rotation strategy if available
            if config and config.proxy_rotation_strategy:
                next_proxy: ProxyConfig = (
                    await config.proxy_rotation_strategy.get_next_proxy()
                )
                if next_proxy:
                    self.logger.info(
                        message="Switch proxy: {proxy}",
                        tag="PROXY",
                        params={"proxy": next_proxy.server},
                    )
                    config.proxy_config = next_proxy
                    # config = config.clone(proxy_config=next_proxy)

            # Fetch fresh content if needed
            if (not cached_result or not html) and content_changed:
                t1 = time.perf_counter()

                if config.user_agent:
                    self.crawler_strategy.update_user_agent(config.user_agent)

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

                ##############################
                # Call CrawlerStrategy.crawl #
                ##############################
                async_response = await self.crawler_strategy.crawl(
                    url,
                    config=config,  # Pass the entire config object
                )

                html = sanitize_input_encode(async_response.html)
                screenshot_data = async_response.screenshot
                pdf_data = async_response.pdf_data
                js_execution_result = async_response.js_execution_result

                t2 = time.perf_counter()
                self.logger.url_status(
                    url=cache_context.display_url,
                    success=bool(html),
                    timing=t2 - t1,
                    tag="FETCH",
                )

                ###############################################################
                # Process the HTML content, Call CrawlerStrategy.process_html #
                ###############################################################
                crawl_result: CrawlResult = await self.aprocess_html(
                    url=url,
                    html=html,
                    extracted_content=extracted_content,
                    config=config,  # Pass the config object instead of individual parameters
                    screenshot_data=screenshot_data,
                    pdf_data=pdf_data,
                    verbose=config.verbose,
                    is_raw_html=True if url.startswith("raw:") else False,
                    redirected_url=async_response.redirected_url,
                    **kwargs,
                )

                crawl_result.status_code = async_response.status_code
                crawl_result.redirected_url = async_response.redirected_url or url
                crawl_result.response_headers = async_response.response_headers
                crawl_result.downloaded_files = async_response.downloaded_files
                crawl_result.js_execution_result = js_execution_result
                crawl_result.mhtml = async_response.mhtml_data
                crawl_result.ssl_certificate = async_response.ssl_certificate
                # Add captured network and console data if available
                crawl_result.network_requests = async_response.network_requests
                crawl_result.console_messages = async_response.console_messages

                crawl_result.success = bool(html)
                crawl_result.session_id = getattr(config, "session_id", None)

                self.logger.url_status(
                    url=cache_context.display_url,
                    success=crawl_result.success,
                    timing=time.perf_counter() - start_time,
                    tag="COMPLETE",
                )

                # Update cache if appropriate
                if cache_context.should_write() and not bool(cached_result):
                    await async_db_manager.acache_url(crawl_result)

                return CrawlResultContainer(crawl_result)

            else:
                self.logger.url_status(
                    url=cache_context.display_url,
                    success=True,
                    timing=time.perf_counter() - start_time,
                    tag="COMPLETE",
                )
                cached_result.success = bool(html)
                cached_result.session_id = getattr(config, "session_id", None)
                cached_result.redirected_url = cached_result.redirected_url or url
                return CrawlResultContainer(cached_result)

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
                error=error_message,
                tag="ERROR",
            )

            return CrawlResultContainer(
                CrawlResult(
                    url=url, html="", success=False, error_message=error_message
                )
            )


if __name__ == "__main__":

    from crawl4ai import AsyncWebCrawler

    AsyncWebCrawler.arun = arun
    AsyncWebCrawler.delete_cached_result = delete_cached_result
    from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher

    # Example usage
    browser_config = BrowserConfig(
        headless=True,
        verbose=True,
    )

    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,
        check_interval=1.0,
        max_session_permit=10,
        monitor=CrawlerMonitor(),
    )

    run_config = CrawlerRunConfig(
        stream=False,
        cache_mode=CacheMode.ENABLED,
        # css_selector="div.eb2",
        # target_elements=["main", "div.eb2"],
        target_elements=["main", "div#content"],
        scan_full_page=True,
        # markdown_generator=DefaultMarkdownGenerator(
        #     content_filter=PruningContentFilter(
        #         threshold=0.48, threshold_type="fixed", min_word_threshold=0
        #     )
        # ),
    )

    async def crawl():
        async with AsyncWebCrawler(config=browser_config) as crawler:

            # TODO tables
            url = "https://uni-osnabrueck.de/studieren/kosten-stipendien-und-foerderung/kosten-des-studiums"
            # url = "https://www.uni-osnabrueck.de/studieren/unsere-studienangebote/abschluesse-und-ordnungen/lehramt-bachelor-und-master/lehramt-an-gymnasien"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung#c31478"
            # url = "https://www.studentenwerk-osnabrueck.de/de/ueber-uns.html"
            # url = "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung"

            urls = [
                "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/bachelorstudiengaenge-zwei-faecher-zulassungsbeschraenkt",
                "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/bachelorstudiengaenge-ein-fach-zulassungsfrei",
                "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/masterstudiengaenge-zwei-faecher",
                "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/masterstudiengaenge-ein-fach",
                "https://www.lili.uni-osnabrueck.de/fachbereich/studium_und_lehre/pruefungsamt/haeufig_gestellte_fragen.html",
            ]
            # url that does not comply with the new website rules (Main content in div.eb2)
            old_url = "https://www.lili.uni-osnabrueck.de/fachbereich/studium_und_lehre/pruefungsamt/haeufig_gestellte_fragen.html"
            old_url_eb1 = "https://www.psycho.uni-osnabrueck.de/studieninteressierte/bachelor_psychologie/studieneignungstest.html"
            results = await crawler.arun(
                url=url,
                # url=old_url_eb1,
                # url=old_url,
                config=run_config,
            )

            # results = await crawler.arun_many(
            #     # url="https://www.ikw.uni-osnabrueck.de/en/research_groups/artificial_intelligence/overview.html",
            #     # url=old_url,
            #     urls=urls,
            #     dispatcher=dispatcher,
            #     config=run_config,
            # )

            # TODO !!! FOR TESTING MAKE SURE TO DELETE THE DB, OTHERWISE THE CACHED RESULTS WILL BE RETURNED
            print(results)

    asyncio.run(crawl())
    print()
