import os
import sys

sys.path.append("/app")
import asyncio
from typing import List

import aiohttp
import dotenv
from crawl4ai import BrowserConfig, CacheMode, CrawlerMonitor, CrawlerRunConfig
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher
from langchain.chains.summarize import load_summarize_chain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter

from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent
from src.chatbot.agents.utils.agent_helpers import llm_optional as sumarize_llm
from src.chatbot.db.redis_client import redis_manager
from src.chatbot.tools.utils.custom_crawl import AsyncOverrideCrawler
from src.chatbot.tools.utils.exceptions import ProgrammableSearchException
from src.chatbot.tools.utils.tool_helpers import decode_string
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

dotenv.load_dotenv()

# TODO Make sure that these urls are reachable
# TODO add the urls to the config file
APPLICATION_CONTEXT_URLS = [
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/zulassungsbeschraenkungen",
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung",
]

# from cashews import cache
# cache.setup("redis://redis:6379")


SEARCH_URL = os.getenv("SEARCH_URL")
MAX_NUM_LINKS = 4


class SearchUniWebTool:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SearchUniWebTool, cls).__new__(cls)
        else:
            cls._instance.anchor_tags = None
        return cls._instance

    def __init__(self):
        if not self.__dict__:  # to avoid reinitializing the object
            self.no_content_found_message = "Content not found"
            self.target_elements = [
                "main",
                "div#content",
            ]
            self.browser_config = BrowserConfig(
                headless=True,
                verbose=True,
            )
            self.run_config = CrawlerRunConfig(
                cache_mode=CacheMode.ENABLED,
                # css_selector="main",
                target_elements=self.target_elements,  # div#content needed for accessing the content from the old website
                scan_full_page=True,
                stream=False,
                # markdown_generator=DefaultMarkdownGenerator(
                #     content_filter=PruningContentFilter(
                #         threshold=0.48, threshold_type="fixed", min_word_threshold=0
                #     )
                # ),
            )
            self.dispatcher = MemoryAdaptiveDispatcher(
                memory_threshold_percent=70.0,
                check_interval=1.0,
                max_session_permit=10,
                monitor=CrawlerMonitor(),
            )

    async def generate_summary(self, text: str, question: str) -> str:
        # TODO summarize the content when it + the prompt +chat_history exceed the number of openai allowed tokens (16385 tokens)
        logger.info(f"Summarizing content, query: {question}")

        # TODO solve for german

        # TODO evaluate how the chunk size affects the results. The idea is to not call the API multiple times
        # converts tokens to characters and divides by 2. Make sure the chunk size is not bigger than the (model) context window
        chunk_size = (
            settings.model.context_window * 4
        ) // 2  # 4 is the average number of characters per token in English
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

        # TODO use aync chain.run?
        settings.llm_summarization_mode = True
        summary = await chain.arun(input_documents=docs, question=question)
        # TODO the summary does not include the Taking from: url
        settings.llm_summarization_mode = False
        return summary

    def compute_tokens(self, search_result_text: str):
        current_search_num_tokens = self.agent_executor.compute_search_num_tokens(
            search_result_text
        )

        total_tokens = self.internal_num_tokens + current_search_num_tokens
        return total_tokens, current_search_num_tokens

    def extract(self, cached_content):
        import ast

        try:
            return ast.literal_eval(cached_content)
        except Exception as e:
            logger.exception(f"Could not extract cached content: {e}")

    async def get_web_content(self, url: str):
        cache_key = f"{__name__}:get_web_content:{url}"

        try:
            # Try to get from cache
            cached_content = await redis_manager.get(cache_key)
            if cached_content:
                logger.debug("[REDIS] Retrieved (creawled) page content from cache")

                return self.extract(cached_content)

            logger.debug("[REDIS] No (crawled) page content cached in Redis")

        except Exception as e:
            logger.error(f"[REDIS] Error accessing (crawled) cache: {e}")

        async with AsyncOverrideCrawler(config=self.browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=self.run_config,
            )
            if result and result[0].success:
                result_url = result[0].url
                result_content = result[0].markdown

                # Cache the result only if greter than 20
                if len(result_content) > 20:
                    cache_value = str((result_url, result_content))
                    await redis_manager.setex(cache_key, redis_manager.TTL, cache_value)
                return result_url, result_content
            return None, None

    async def visit_urls_extract(
        self,
        url: str,
        about_application: bool,
        max_num_links: int = MAX_NUM_LINKS,
        do_not_visit_links: List = [],
    ) -> tuple[List, list]:

        # get num tokens (prompt + chat history+query)
        self.internal_num_tokens = self.agent_executor.compute_internal_tokens(
            self.query
        )

        contents = []
        self.links_search = []

        async with aiohttp.ClientSession() as session:

            # query google search API
            async with session.get(url) as response:
                response.raise_for_status()

                if response.status != 200:

                    raise ProgrammableSearchException(
                        f"Failed: Programmable Search Engine. Status: {response.status}"
                    )
                # parse json response
                dict_response = await response.json()

                # extract search results

                # check if there are results
                total_results = dict_response.get("searchInformation", {}).get(
                    "totalResults", 0
                )
                if int(total_results) > 0:

                    self.links_search = [
                        item["link"] for item in dict_response["items"]
                    ]
                    logger.debug(
                        f"[ProgrammableSearch] Search Engine retuned {len(self.links_search)} results (links)"
                    )
                else:
                    logger.warning(
                        f"[ProgrammableSearch] No results found by the search engine while requesting this URL: {url}"
                    )
                    return [], []

        urls = []
        for i, href in enumerate(self.links_search):
            # href = str(tag.get("href"))s
            # Check for previously visited links
            if href.endswith(".pdf"):
                # TODO pdf files need to be handled differently (Vector DB for example)
                continue

            if len(urls) >= max_num_links:
                if about_application:
                    for url_ in APPLICATION_CONTEXT_URLS:
                        if url_ in urls or url_ in do_not_visit_links:
                            continue
                        urls.append(url_)

                break

            # Links that were visited in a graph run should not be visited again
            if href in urls or href in do_not_visit_links:
                continue

            urls.append(href)

        if urls:

            for url in urls:

                result_url, result_content = await self.get_web_content(url)

                if result_content:
                    if len(result_content) < 20:
                        logger.warning(
                            f"[Crawling] The URL content could not be extracted. Make sure the content is contained in current target elements: {self.target_elements}. URL: {url}"
                        )
                        continue
                    contents.append(
                        f"Information taken from: {result_url}\n{result_content}"
                    )

        # summarize the content if the total tokens exceed the limit
        # TODO this needs to be async and generate summary cached
        if contents:
            # order the contents by the index
            contents = sorted(contents, key=lambda x: x[1])
            # contents = [x[0] for x in contents]
            total_tokens, _ = self.compute_tokens("".join(contents))
            if total_tokens > settings.model.context_window:
                for i, text in enumerate(reversed(contents)):
                    # original_index = len(contents) - i - 1
                    # start summarizing from the last text fetched (assumed to be the least important/relevant)
                    contents[i] = await self.generate_summary(text, self.query)
                    # update the total tokens
                    total_tokens, _ = self.compute_tokens("".join(contents))
                    if total_tokens <= settings.model.context_window:
                        break

        return urls, contents

    async def arun(self, **kwargs):
        try:
            # Initialize Redis if needed
            await redis_manager.ensure_connection()

            self.query = kwargs["query"]
            query_url = decode_string(self.query)
            url = SEARCH_URL + query_url

            cache_key = f"{__name__}:arun:{url}"
            # try to get cached content

            cached_content = await redis_manager.get(cache_key)
            if cached_content:
                logger.debug("[REDIS] Retrieved cached searched results (urls) ")
                return self.extract(cached_content)

            self.agent_executor = CampusManagementOpenAIToolsAgent.run()

            visited_urls, contents = await self.visit_urls_extract(
                url=url,
                about_application=kwargs["about_application"],
                do_not_visit_links=kwargs["do_not_visit_links"],
            )

            final_output = "\n".join(contents)

            if final_output:
                # for tesing
                # TODO REMOVE
                final_output_tokens, final_search_tokens = self.compute_tokens(
                    final_output
                )
                logger.info(f"Search tokens: {final_search_tokens}")
                logger.info(f"Final output (search + prompt): {final_output_tokens}")
                # settings.final_output_tokens.append(final_output_tokens)
                # settings.final_search_tokens.append(final_search_tokens)

                # cache results
                if len(final_output) > 20:
                    cache_value = str((final_output, visited_urls))
                    await redis_manager.client.setex(
                        cache_key, redis_manager.TTL, cache_value
                    )

            return (final_output, visited_urls) if contents else ([], [])

        except ProgrammableSearchException as e:
            logger.exception(f"Error: search engine: {e}", exc_info=True)
            raise ProgrammableSearchException(
                f"Failed: Programmable Search Engine. Status: {e}"
            )

        except Exception as e:
            logger.exception(f"Error while searching the web: {e}", exc_info=True)
            # return "Error while searching the web"
            return [], []

    def __del__(self):
        """Cleanup when the instance is destroyed."""
        if redis_manager.client:
            asyncio.create_task(redis_manager.cleanup())

    def run(
        self,
        **kwargs,
    ) -> tuple[str, list]:
        """
        Searches the University of Osnabrück website based on the given query.

        Args:
            query (str): The query to search for.


        Returns:
            str: The search result text.

        Notes:
            - This function is specifically designed to handle questions about the University of Osnabrück, such as the application process or studying at the university.

        """
        return asyncio.run(self.arun(**kwargs))


search_uni_web = SearchUniWebTool()


if __name__ == "__main__":
    # use for testing/ debugging

    try:
        from search_sample import search_sample
    except ImportError:

        sys.path.append("./test")
        from search_sample import search_sample

    search_uni_web_instance = SearchUniWebTool()
    query = "can I study Biology?"
    search_result = search_uni_web_instance.run(query)
    search_result_2 = search_uni_web_instance.run(query)

    print(search_result)
