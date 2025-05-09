import os
import sys

sys.path.append("/app")
import asyncio
from typing import List

import aiohttp
import dotenv
import streamlit as st
from aiohttp import ClientSession

# https://github.com/Krukov/cashews?tab=readme-ov-file#template-keys
from cashews import cache
from crawl4ai import (
    BrowserConfig,
    CacheMode,
    CrawlerMonitor,
    CrawlerRunConfig,
    DisplayMode,
)
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from langchain.chains.summarize import load_summarize_chain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter

from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent
from src.chatbot.agents.utils.agent_helpers import llm_optional as sumarize_llm
from src.chatbot.tools.utils.custom_crawl import AsyncOverrideCrawler
from src.chatbot.tools.utils.exceptions import ProgrammableSearchException
from src.chatbot.tools.utils.tool_helpers import decode_string
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

# cache.setup("mem://?size=1000000&check_interval=5")
# TODO Connect cache with a DB, Redis??
cache.setup("mem://", size=1000)

dotenv.load_dotenv()

# TODO Make sure that these urls are reachable
# TODO add the urls to the config file
APPLICATION_CONTEXT_URLS = [
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung/zulassungsbeschraenkungen",
    # "https://www.uni-osnabrueck.de/studieren/bewerbung-und-studienstart/bewerbung-zulassung-und-einschreibung",
]


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
            self.browser_config = BrowserConfig(
                headless=True,
                verbose=True,
            )
            self.run_config = CrawlerRunConfig(
                cache_mode=CacheMode.ENABLED,
                # css_selector="main",
                target_elements=[
                    "main",
                    "div.eb2",
                ],  # eb2 is the class for the main content (old website)
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

    async def visit_urls_extract(
        self,
        url: str,
        about_application: bool,
        max_num_links: int = MAX_NUM_LINKS,
        do_not_visit_links: List = [],
    ) -> tuple[str, list]:

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
                dict_reponse = await response.json()

                # extract search results
                self.links_search = [item["link"] for item in dict_reponse["items"]]

        urls = []
        for i, href in enumerate(self.links_search):
            # href = str(tag.get("href"))
            # Check for previously visited links
            if href.endswith(".pdf"):
                # TODO pdf files need to be handled differently (Vector DB for example)
                continue

            if i >= max_num_links:
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
            # async with AsyncOverrideCrawler(config=self.browser_config) as crawler:
            #     results = await crawler.arun_many(
            #         urls=urls,
            #         config=self.run_config,
            #         dispatcher=self.dispatcher,
            #     )
            #     if results:
            #         for result in results:
            #             if result.success:
            #                 contents.append(
            #                     f"Information taken from: {result.url}\n{result.markdown}"
            #                 )

            for url in urls:
                async with AsyncOverrideCrawler(config=self.browser_config) as crawler:
                    result = await crawler.arun(
                        url=url,
                        config=self.run_config,
                    )
                    if result:
                        if result[0].success:
                            contents.append(
                                f"Information taken from: {result[0].url}\n{result[0].markdown}"
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

    def run(
        self,
        # query: str,
        # about_application: bool = False,
        # single_subject: bool = False,
        # two_subject: bool = False,
        # teaching_degree: bool = False,
        # do_not_visit_links: List = None,
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

        try:
            # TODO FIX dependency injection and circular dependency/import
            self.agent_executor = CampusManagementOpenAIToolsAgent.run()
            self.query = kwargs["query"]
            query_url = decode_string(self.query)
            url = SEARCH_URL + query_url

            visited_urls, contents = asyncio.run(
                self.visit_urls_extract(
                    url=url,
                    about_application=kwargs["about_application"],
                    do_not_visit_links=kwargs["do_not_visit_links"],
                )
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

            return (
                (final_output, visited_urls)
                if contents
                else (self.no_content_found_message, visited_urls)
            )

        except ProgrammableSearchException as e:
            logger.exception(f"Error: search engine: {e}", exc_info=True)
            raise ProgrammableSearchException(
                f"Failed: Programmable Search Engine. Status: {e}"
            )

        except Exception as e:
            logger.exception(f"Error while searching the web: {e}", exc_info=True)
            return "Error while searching the web"


search_uni_web = SearchUniWebTool()


if __name__ == "__main__":
    # use for testing/ debugging

    try:
        from search_sample import search_sample
    except ImportError:

        sys.path.append("./test")
        from search_sample import search_sample

    # content, anchor_tags = extract_and_visit_links(search_sample)

    # @cache(ttl="2h")
    # def test_cache(user_input):
    #     print("function called")

    # for i in range(5):
    #     test_cache("test")

    # test_cache("test2")

    search_uni_web_instance = SearchUniWebTool()
    # query = "PO-Bachelor-Cognitive Science pdf"
    query = "can I study Biology?"
    search_result = search_uni_web_instance.run(query)
    search_result_2 = search_uni_web_instance.run(query)

    print(search_result)
