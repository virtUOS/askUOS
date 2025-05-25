import os
import sys

sys.path.append("/app")
import asyncio
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import dotenv
import nest_asyncio
import redis.asyncio as redis
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerMonitor,
    CrawlerRunConfig,
)
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher
from langchain.chains.summarize import load_summarize_chain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter

from src.chatbot.agents.utils.agent_helpers import llm_optional as sumarize_llm

# from src.chatbot.db.redis_client import redis_manager
from src.chatbot.tools.utils.custom_crawl import arun, delete_cached_result
from src.chatbot.tools.utils.exceptions import ProgrammableSearchException
from src.chatbot.tools.utils.tool_helpers import decode_string
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

AsyncWebCrawler.arun = arun
AsyncWebCrawler.delete_cached_result = delete_cached_result

dotenv.load_dotenv()

# Application context URLs
APPLICATION_CONTEXT_URLS = [
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/zulassungsbeschraenkungen",
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung",
]

SEARCH_URL = os.getenv("SEARCH_URL")
MAX_NUM_LINKS = 4


TTL = 30 * 60 * 60  # 30h default TTL

# Module-level state variables
_initialized = False
_init_lock = asyncio.Lock()
no_content_found_message = "Content not found"
target_elements = ["main", "div#content"]
browser_config = None
run_config = None
dispatcher = None


async def initialize_redis(client: redis.Redis):
    """Initialize Redis connection and settings."""

    try:
        await client.ping()
        logger.info("[REDIS] Redis connection established successfully.")
        info = await client.info("memory")
        used_memory_mb = int(info["used_memory"]) / 1024 / 1024
        logger.info(
            f"[REDIS] Redis configured successfully. Memory usage: {used_memory_mb:.2f}MB"
        )
    except redis.ConnectionError as e:
        logger.error(f"[REDIS] Redis connection error: {e}")
        raise


async def ensure_initialized():
    """Ensure that the module is initialized only once."""
    global _initialized, browser_config, run_config, dispatcher

    if not _initialized:
        async with _init_lock:
            if not _initialized:
                browser_config = BrowserConfig(
                    headless=True,
                    verbose=True,
                )
                run_config = CrawlerRunConfig(
                    cache_mode=CacheMode.ENABLED,
                    target_elements=target_elements,
                    scan_full_page=True,
                    verbose=settings.application.debug,
                    stream=False,
                )
                dispatcher = MemoryAdaptiveDispatcher(
                    memory_threshold_percent=70.0,
                    check_interval=1.0,
                    max_session_permit=10,
                    monitor=CrawlerMonitor(),
                )

                _initialized = True


def extract_cached_content(cached_content):
    """Extract cached content from string representation."""
    import ast

    try:
        return ast.literal_eval(cached_content)
    except Exception as e:
        logger.exception(f"Could not extract cached content: {e}")
        return None


async def generate_summary(text: str, query: str) -> str:
    """Generate a summary of the provided text."""
    logger.info(f"Summarizing content, query: {query}")

    chunk_size = (settings.model.context_window * 4) // 2
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n"], chunk_size=chunk_size, chunk_overlap=300
    )
    docs = text_splitter.create_documents([text])

    reduce_template_string = """Your task it to create a concise summary of the text provided. 
## Instruction: Your task is to generate a concise and accurate summary of the provided text. The summary should effectively capture the key points and concepts while strictly avoiding any interpretations or subjective additions.
1. Focus on Relevance: Emphasize information that directly addresses the question/query specified below.
2. Handling External Sources: Do not condense or modify links/urls or references to external sources; include them as they appear in the original text.
3. Tables and Data: If the text includes tables, avoid summarizing their contents. Instead, include them in their entirety within the summary.
4. Language Consistency: Ensure the summary is written in the same language as the original text.
4. Formatting: Present the summary in markdown format, which should encompass all necessary elements, including tables and code blocks, without alterations.

    Summarize this text:
    {text}

    question/query: {question}
    Answer:
    """

    reduce_template = PromptTemplate(
        template=reduce_template_string, input_variables=["text", "question"]
    )

    chain = load_summarize_chain(
        llm=sumarize_llm(),
        chain_type="map_reduce",
        map_prompt=reduce_template,
        combine_prompt=reduce_template,
        verbose=True,
    )

    settings.llm_summarization_mode = True
    summary = await chain.arun(input_documents=docs, question=query)
    settings.llm_summarization_mode = False
    return summary


def compute_tokens(
    search_result_text: str, query: str, agent_executor
) -> Tuple[int, int]:
    """Compute tokens for the search result text."""
    internal_num_tokens = agent_executor.compute_internal_tokens(query)
    current_search_num_tokens = agent_executor.compute_search_num_tokens(
        search_result_text
    )
    total_tokens = internal_num_tokens + current_search_num_tokens
    return total_tokens, current_search_num_tokens


async def get_web_content(
    url: str, client: redis.Redis
) -> Tuple[Optional[str], Optional[str]]:
    """Get web content from URL with caching."""
    await ensure_initialized()
    cache_key = f"{__name__}:get_web_content:{url}"

    result_content = None
    result_url = None
    try:
        # Try to get from cache
        cached_content = await client.get(cache_key)
        if cached_content:
            logger.debug("[REDIS] Retrieved (crawled) page content from cache")
            return extract_cached_content(cached_content)

        logger.debug("[REDIS] No (crawled) page content cached in Redis")

    except Exception as e:
        logger.error(f"[REDIS] Error accessing (crawled) cache: {e}")

    try:
        async with AsyncWebCrawler(
            config=browser_config,
            thread_safe=True,
        ) as crawler:
            result = await crawler.arun(
                url=url,
                config=run_config,
            )
            if result and result[0].success:
                result_url = result[0].url
                result_content = result[0].markdown

            return result_url, result_content

    except Exception as e:
        logger.exception(f"Error while crawling the URL: {url}", exc_info=True)
        return result_url, result_content
    finally:
        # Cache the result
        if result_content and len(result_content) > 20:
            cache_value = str((result_url, result_content))
            try:
                await client.setex(cache_key, TTL, cache_value)
            except Exception as e:
                logger.exception(
                    f"Error while caching content for URL: {url}", exc_info=True
                )


async def visit_urls_extract(
    url: str,
    query: str,
    agent_executor,
    about_application: bool = False,
    max_num_links: int = MAX_NUM_LINKS,
    do_not_visit_links: List = [],
    client: redis.Redis = None,
) -> Tuple[List, List]:
    """Visit URLs and extract content."""
    contents = []
    links_search = []

    async with aiohttp.ClientSession() as session:
        # Query Google search API
        async with session.get(url) as response:
            response.raise_for_status()

            if response.status != 200:
                raise ProgrammableSearchException(
                    f"Failed: Programmable Search Engine. Status: {response.status}"
                )

            # Parse JSON response
            dict_response = await response.json()

            # Check if there are results
            total_results = dict_response.get("searchInformation", {}).get(
                "totalResults", 0
            )
            if int(total_results) > 0:
                links_search = [item["link"] for item in dict_response["items"]]
                logger.debug(
                    f"[ProgrammableSearch] Search Engine returned {len(links_search)} results (links)"
                )
            else:
                logger.warning(
                    f"[ProgrammableSearch] No results found by the search engine while requesting this URL: {url}"
                )
                return [], []

    urls = []
    for href in links_search:
        # Skip PDF files
        if href.endswith(".pdf"):
            continue

        if len(urls) >= max_num_links:
            if about_application:
                for url_ in APPLICATION_CONTEXT_URLS:
                    if url_ in urls or url_ in do_not_visit_links:
                        continue
                    urls.append(url_)
            break

        # Skip already visited links
        if href in urls or href in do_not_visit_links:
            continue

        urls.append(href)

    if urls:
        for url in urls:
            result_url, result_content = await get_web_content(url, client)

            if result_content:
                if len(result_content) < 20:
                    logger.warning(
                        f"[Crawling] The URL content could not be extracted. Make sure the content is contained in current target elements: {target_elements}. URL: {url}"
                    )
                    continue
                contents.append(
                    f"Information taken from: {result_url}\n{result_content}"
                )

    # Summarize content if total tokens exceed the limit
    if contents:
        # Order the contents by the index
        contents = (
            sorted(contents, key=lambda x: x[1])
            if isinstance(contents[0], tuple)
            else contents
        )
        total_tokens, _ = compute_tokens("".join(contents), query, agent_executor)

        if total_tokens > settings.model.context_window:
            for i, text in enumerate(reversed(contents)):
                contents[i] = await generate_summary(text, query)
                # Update the total tokens
                total_tokens, _ = compute_tokens(
                    "".join(contents), query, agent_executor
                )
                if total_tokens <= settings.model.context_window:
                    break

    return urls, contents


async def async_search(client, **kwargs) -> Tuple[str, List]:
    """Asynchronous search function that encapsulates the search functionality."""
    await ensure_initialized()
    try:
        # Initialize Redis if needed
        # await redis_manager.ensure_connection()
        query = kwargs.get("query", "")
        query_url = decode_string(query)
        url = SEARCH_URL + query_url
        do_not_visit_links = kwargs.get("do_not_visit_links", [])
        about_application = kwargs.get("about_application", False)

        cache_key = f"{__name__}:async_search:{url}"
        # Try to get cached content
        cached_content = await client.get(cache_key)
        if cached_content:
            logger.debug("[REDIS] Retrieved cached searched results (urls)")
            return extract_cached_content(cached_content)

        agent_executor = kwargs["agent_executor"]

        visited_urls, contents = await visit_urls_extract(
            url=url,
            query=query,
            agent_executor=agent_executor,
            about_application=about_application,
            do_not_visit_links=do_not_visit_links,
            client=client,
        )

        final_output = "\n".join(contents)

        if final_output:
            # For testing
            final_output_tokens, final_search_tokens = compute_tokens(
                final_output, query, agent_executor
            )
            logger.info(f"Search tokens: {final_search_tokens}")
            logger.info(f"Final output (search + prompt): {final_output_tokens}")

            # Cache results
            if len(final_output) > 20:
                cache_value = str((final_output, visited_urls))
                await client.setex(cache_key, TTL, cache_value)

        return (final_output, visited_urls) if contents else ([], [])

    except ProgrammableSearchException as e:
        logger.exception(f"Error: search engine: {e}", exc_info=True)
        raise ProgrammableSearchException(
            f"Failed: Programmable Search Engine. Status: {e}"
        )

    except Exception as e:
        logger.exception(f"Error while searching the web: {e}", exc_info=True)
        return [], []


def search_uni_web(**kwargs) -> Tuple[str, List]:
    """
    Searches the University of Osnabrück website based on the given query.
    Handles both threaded and async execution contexts safely.
    """

    try:
        try:
            loop = asyncio.get_running_loop()
            nest_asyncio.apply()
            logger.debug("Running within an existing event loop")
            client = redis.Redis(host="redis", port=6379, decode_responses=True)
            return asyncio.run_coroutine_threadsafe(
                async_search(client, **kwargs), loop
            ).result()
        except RuntimeError:

            async def complete_search_flow():
                client = redis.Redis(host="redis", port=6379, decode_responses=True)
                await initialize_redis(client)
                result = await async_search(client, **kwargs)
                await client.close()
                return result

            return asyncio.run(complete_search_flow())
    except Exception as e:
        logger.exception(f"Error in search execution: {str(e)}")
        return [], []

    # try:
    #     # Get the current event loop or create a new one
    #     try:
    #         loop = asyncio.get_running_loop()
    #         # If we're inside a running loop, we'll use nest_asyncio to allow nesting
    #         nest_asyncio.apply()
    #         logger.debug("Running within an existing event loop")
    #         return asyncio.run_coroutine_threadsafe(
    #             async_search(**kwargs), loop
    #         ).result()
    #     except RuntimeError:

    #         # No running event loop, create a fresh one and run directly

    #         # Define a complete async function that initializes, executes and cleans up
    #         async def complete_search_flow():
    #             global client

    #             # Create new Redis connection for this event loop session
    #             client = redis.Redis(host="redis", port=6379, decode_responses=True)

    #             try:
    #                 # Initialize Redis
    #                 await initialize_redis()
    #                 # Execute search
    #                 result = await async_search(**kwargs)
    #                 return result
    #             except Exception as e:
    #                 logger.exception(f"Error during search flow: {str(e)}")
    #                 return [], []

    #         # Run everything in a single event loop lifecycle
    #         return asyncio.run(complete_search_flow())

    # No running event loop, create a fresh one and run directly

    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)

    # # Ensure Redis is initialized with this loop
    # async def setup_and_search():
    #     await initialize_redis()
    #     return await async_search(**kwargs)

    # return asyncio.run(setup_and_search())

    # try:
    #     result = loop.run_until_complete(setup_and_search())
    # finally:
    #     try:
    #         loop.run_until_complete(loop.shutdown_asyncgens())
    #     finally:
    #         loop.close()
    #         return result

    # return asyncio.run_coroutine_threadsafe(
    #     async_search(**kwargs), loop
    # ).result()
    # return asyncio.run(async_search(**kwargs))
    # except Exception as e:
    #     logger.exception(f"Error in search execution: {str(e)}")
    #     return [], []


if __name__ == "__main__":
    # Use for testing/debugging
    try:
        from search_sample import search_sample
    except ImportError:
        sys.path.append("./test")
        from search_sample import search_sample

    query = "can I study Biology?"
    search_result = search_uni_web(query=query)
    search_result_2 = search_uni_web(query=query)

    print(search_result)
