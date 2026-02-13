import os
import sys

sys.path.append("/app")
import asyncio
from typing import List, Optional, Tuple

import aiohttp

# At the beginning of your script
import colorama
import dotenv
import nest_asyncio
import redis.asyncio as aioredis
import redis.asyncio as redis
from langchain_classic.chains.summarize import load_summarize_chain
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate

from src.chatbot.agents.models import RetrievalResult, ScrapeResult
from src.chatbot.agents.utils.agent_helpers import llm_optional as sumarize_llm
from src.chatbot.tools.utils.exceptions import ProgrammableSearchException
from src.chatbot.tools.utils.tool_helpers import decode_string
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

colorama.init(strip=True)


dotenv.load_dotenv()

# from src.chatbot.db.redis_pool import RedisPool
# service running on docker compose
CRAWL_API_URL = "http://crawl4ai:11235/crawl"
# Application context URLs
APPLICATION_CONTEXT_URLS = [
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/zulassungsbeschraenkungen",
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung",
]

SEARCH_URL = os.getenv("SEARCH_URL")
MAX_NUM_LINKS = 4

# TODO Change cache mechanism
CRAWL_PAYLOAD = {
    "browser_config": {"type": "BrowserConfig", "params": {"headless": True}},
    "crawler_config": {
        "type": "CrawlerRunConfig",
        "params": {
            "stream": False,
            "cache_mode": {"type": "CacheMode", "params": "bypass"},
            "word_count_threshold": 100,
            "target_elements": ["main", "div#content"],
            "scan_full_page": True,
        },
    },
}

TTL = 48 * 60 * 60  # 48h default TTL

no_content_found_message = "Content not found"


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


async def generate_summary(text: str, query: str) -> str:
    """Generate a summary of the provided text."""
    logger.info(f"[LMM-OPERATION] Summarizing content, query: {query}")

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


async def crawl_urls_via_api(
    urls: List[str], crawl_payload: Optional[dict] = CRAWL_PAYLOAD
) -> List[ScrapeResult]:
    """
    Crawl multiple URLs using the API endpoint.
    Returns a list of crawl results.
    """

    try:
        scraped_results = []
        payload = crawl_payload
        payload["urls"] = urls
        payload["crawler_config"]["params"][
            "stream"
        ] = False  # ensure non-streaming mode
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CRAWL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    # Wait for the complete response
                    response_data = await response.json()

                    # Extract results from the response
                    if response_data.get("success") is False:
                        logger.error("Crawl API reported failure: ")
                        return []

                    results_data: List[dict] = response_data.get("results", [])

                    for result_data in results_data:
                        scraped_results.append(
                            ScrapeResult(
                                url=result_data["url"],
                                html=result_data["html"],
                                cleaned_html=result_data["cleaned_html"],
                                markdown=result_data["markdown"]["raw_markdown"],
                                title=result_data["metadata"]["title"],
                                description=result_data["metadata"]["description"],
                                keywords=result_data["metadata"]["keywords"],
                                author=result_data["metadata"]["author"],
                                # links=result_data["links"],
                            )
                        )
                    return scraped_results
    except Exception as e:
        logger.error(f"[SCRAPING]Exception while crawling via API: {e}")
        return []


async def extract_url_redis(
    url: str, cache_key: str, client: redis.Redis
) -> ScrapeResult | str:

    # Try to get from cache
    cached_content = await client.get(cache_key)
    print(f"----------------searching key: {cache_key}------------")
    if cached_content:
        logger.debug("[REDIS] Retrieved (crawled) page content from cache")
        return ScrapeResult.from_json(cached_content)
        # return extract_cached_content(cached_content)

    logger.debug("[REDIS] No (crawled) page content cached in Redis")
    return url


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
    scraping_result = []
    filtered_urls = []
    cache_key_prefix = f"{__name__}:visit_urls_extract:"
    cache_tasks = []
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
                    f"[SEARCH] Search Engine returned {len(links_search)} results (links)"
                )
            else:
                logger.warning(
                    f"[SEARCH] No results found by the search engine while requesting this URL: {url}"
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

    # Check if url is in cache
    print(await client.keys("*"))
    task_url_cache = [
        extract_url_redis(url=u, cache_key=f"{cache_key_prefix}{u}", client=client)
        for u in urls
    ]
    task_url_cache_result = await asyncio.gather(
        *task_url_cache, return_exceptions=True
    )
    for c in task_url_cache_result:
        if isinstance(c, str):
            filtered_urls.append(c)
        elif isinstance(c, ScrapeResult):
            contents.append(c.formatted_markdown)  # ← use cached content immediately
        elif isinstance(c, Exception):
            logger.error(f"[REDIS] Error accessing (crawled) cache: {c}")

    if filtered_urls:
        scraping_result = await crawl_urls_via_api(filtered_urls)
        # scraping_result.extend(freshly_scraped)
    for scraped in scraping_result:
        # result_url, result_content = await get_web_content(url, client)

        if scraped.formatted_markdown and len(scraped.formatted_markdown) >= 70:
            cache_key = f"{cache_key_prefix}{scraped.url}"
            print(f"----------------saving key {cache_key}----------------")
            # await client.setex(cache_key, TTL, scraped.to_json())
            cache_tasks.append(
                asyncio.create_task(client.setex(cache_key, TTL, scraped.to_json()))
            )
            contents.append(scraped.formatted_markdown)

    # Summarize content if total tokens exceed the limit
    try:
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
    finally:
        c_result = await asyncio.gather(*cache_tasks, return_exceptions=True)
        for cr in c_result:
            if isinstance(cr, Exception):
                logger.exception(
                    f"[REDIS] Error while caching content for URL: {cr}",
                )
    # print(await client.keys("*"))
    return urls, contents


async def async_search(**kwargs) -> Tuple[str, List]:
    """Asynchronous search function that encapsulates the search functionality."""
    try:
        # client = redis.Redis(host="redis", port=6379, decode_responses=True)
        client = aioredis.Redis(host="redis", port=6379, decode_responses=True)
        # await RedisPool.get_pool()
        # client = RedisPool.get_client()
        try:
            query = kwargs.get("query", "")
            query_url = decode_string(query)
            url = SEARCH_URL + query_url
            do_not_visit_links = kwargs.get("do_not_visit_links", [])
            about_application = kwargs.get("about_application", False)

            # Try to get cached content
            cache_key = f"{__name__}:async_search:{url}"
            cached_content = await client.get(cache_key)
            if cached_content:
                logger.debug("[REDIS] Retrieved cached searched results (urls)")
                return RetrievalResult.from_json(cached_content)

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
                logger.info(f"[SEARCH] Search tokens: {final_search_tokens}")
                logger.info(
                    f"[SEARCH] Final output (search + prompt): {final_output_tokens}"
                )

            retrieved = RetrievalResult(
                result_text=final_output, reference=visited_urls, search_query=query
            )
            # Cache results
            if len(final_output) > 20:
                await client.setex(cache_key, TTL, retrieved.to_json())

            return retrieved
        finally:
            await client.aclose()
    except redis.ConnectionError as e:
        logger.error(f"It was not possible to establish a connection to Redis: {e}")
        raise redis.ConnectionError("Redis Failed") from e
    except ProgrammableSearchException as e:
        logger.exception(f"[SEARCH] Error: search engine: {e}", exc_info=True)
        raise ProgrammableSearchException(
            f"Failed: Programmable Search Engine. Status: {e}"
        )
    except Exception as e:
        logger.exception(f"[SEARCH] Error while searching the web: {e}", exc_info=True)
        raise


# def search_uni_web(**kwargs) -> Tuple[str, List]:
#     """
#     Searches the University of Osnabrück website based on the given query.
#     Handles both threaded and async execution contexts safely.
#     """

#     try:
#         try:
#             loop = asyncio.get_running_loop()
#             nest_asyncio.apply()
#             logger.debug("[SYSTEM] Running within an existing event loop")
#             client = redis.Redis(host="redis", port=6379, decode_responses=True)
#             return asyncio.run_coroutine_threadsafe(
#                 async_search(client, **kwargs), loop
#             ).result()
#         except RuntimeError:

#             async def complete_search_flow():
#                 client = redis.Redis(host="redis", port=6379, decode_responses=True)
#                 await initialize_redis(client)
#                 result = await async_search(client, **kwargs)
#                 await client.close()
#                 return result

#             return asyncio.run(complete_search_flow())
#     except Exception as e:
#         logger.exception(f"[SEARCH] Error in search execution: {str(e)}")
#         return [], []


if __name__ == "__main__":
    # Use for testing/debugging
    import asyncio

    import redis.asyncio as aioredis

    async def test():
        client = aioredis.Redis(host="redis", port=6379, decode_responses=True)
        await client.setex("test_key", 300, "hello")
        val = await client.get("test_key")
        print(f"Stored and retrieved: {val}")  # Should print "hello"
        await client.aclose()

    asyncio.run(test())


# async def get_web_content(url: str, client: redis.Redis) -> ScrapeResult:
#     """Get web content from URL with caching."""
#     # esure crawl is initialized
#     await ensure_initialized()
#     cache_key = f"{__name__}:get_web_content:{url}"

#     result_content = None
#     result_url = None
#     try:
#         # Try to get from cache
#         cached_content = await client.get(cache_key)
#         if cached_content:
#             logger.debug("[REDIS] Retrieved (crawled) page content from cache")
#             return extract_cached_content(cached_content)

#         logger.debug("[REDIS] No (crawled) page content cached in Redis")

#     except Exception as e:
#         logger.error(f"[REDIS] Error accessing (crawled) cache: {e}")

#     results = crawl_urls_via_api()
#     try:
#         async with AsyncWebCrawler(
#             config=browser_config,
#             thread_safe=True,
#         ) as crawler:
#             result = await crawler.arun(
#                 url=url,
#                 config=run_config,
#             )
#             if result and result[0].success:
#                 result_url = result[0].url
#                 result_content = result[0].markdown

#             return ScrapeResult(result_url=result_url, result_content=result_content)

#     except Exception as e:
#         logger.exception(f"[CRAWL] Error while crawling the URL: {url}", exc_info=True)
#         return ScrapeResult(result_url=result_url, result_content=result_content)
#     finally:
#         # Cache the result
#         if result_content and len(result_content) > 20:
#             # cache_value = str((result_url, result_content))
#             try:
#                 await client.setex(cache_key, TTL, cache_value.to_json())
#             except Exception as e:
#                 logger.exception(
#                     f"[REDIS] Error while caching content for URL: {url}", exc_info=True
#                 )
