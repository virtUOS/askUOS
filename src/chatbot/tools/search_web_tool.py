import sys

sys.path.append("/app")


from langchain_core.pydantic_v1 import BaseModel, Field, PrivateAttr
import dotenv
import requests
import asyncio
import aiohttp

from langchain.chains.summarize import load_summarize_chain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from aiohttp import ClientSession
from src.chatbot.tools.utils.tool_helpers import (
    decode_string,
    extract_html_text,
    extract_pdf_text,
    visited_links,
    VisitedLinks,
)
from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent

from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings
from bs4 import BeautifulSoup

# https://github.com/Krukov/cashews?tab=readme-ov-file#template-keys
from cashews import cache

# cache.setup("mem://?size=1000000&check_interval=5")
# TODO Connect cache with a DB, Redis??
cache.setup("mem://", size=1000)

dotenv.load_dotenv()


SEARCH_URL = settings.search_config.search_url
SERVICE = settings.search_config.service
MAX_NUM_LINKS = 4
HEADLESS_OPTION = "--headless"


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
            firefox_options = Options()
            firefox_options.add_argument(HEADLESS_OPTION)
            service = Service(SERVICE)
            self.driver = webdriver.Firefox(service=service, options=firefox_options)

    def __del__(self):
        self.driver.quit()

    def generate_summary(self, text: str, question: str) -> str:
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
    The summary must capture the key points and concepts from the original text without adding interpretations. Focus on the information that can be helpful in order
    to answer the question/query provided below. Make sure that you DO NOT summarize/shorten links or references to external sources.

    Summarize this text:
    {text}

    question/query: {question}
    Answer:
    """

        reduce_template = PromptTemplate(
            template=reduce_template_string, input_variables=["text", "question"]
        )
        chain = load_summarize_chain(
            llm=self.agent_executor.llm,
            chain_type="map_reduce",
            map_prompt=reduce_template,
            combine_prompt=reduce_template,
            verbose=True,
        )

        # TODO use aync chain.run?
        settings.llm_summarization_mode = True
        summary = chain.run(input_documents=docs, question=question)
        # TODO the summary does not include the Taking from: url
        settings.llm_summarization_mode = False
        return summary

    def compute_tokens(self, search_result_text: str):
        current_search_num_tokens = self.agent_executor.compute_search_num_tokens(
            search_result_text
        )

        total_tokens = self.internal_num_tokens + current_search_num_tokens
        return total_tokens, current_search_num_tokens

    async def fetch_url(self, session: ClientSession, url: str) -> str:
        """
        Fetches the content from a given URL asynchronously.
        Args:
            session (ClientSession): The aiohttp client session to use for making the request.
            url (str): The URL to fetch content from.
        Returns:
            str: The extracted text content from the URL, prefixed with a source information string.
                Returns None if an error occurs or the response status is not 200.
        Raises:
            Exception: Logs any exceptions that occur during the fetch process.
        """

        # TODO the function needs to return the text fetched from the URL
        @cache(ttl="2h")
        async def process_url(url):

            taken_from = "Information taken from: "
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        # TODO pdf files need to be handled differently (Vector DB for example)
                        if url.endswith(".pdf"):
                            # TODO read pdf using response.stream(), so that the whole pdf is not loaded into memory. Process every stream
                            # TODO as soon as it is available (see online algorithm)
                            pdf_bytes = (
                                await response.read()
                            )  # Read PDF content as bytes
                            text = (
                                f"{taken_from}{url}\n{extract_pdf_text(url, pdf_bytes)}"
                            )
                        else:
                            html_content = await response.text()
                            text = f"{taken_from}{url}\n{extract_html_text(url, html_content)}"

                        # if text:
                        # self.contents.append(text)
                        # total_tokens, _ = self.compute_tokens(
                        #     "".join(self.contents)
                        # )
                        # # 1 token ~= 4 chars in English  --> https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them
                        # if total_tokens > settings.model.context_window:

                        #     # TODO generate_summary must be async and the chain inside it must be awaited (use async chain.run)
                        #     text = self.generate_summary(text, self.query)
                        #     self.contents[-1] = text

                        return text
                    return f"Error fetching content from: {url}"

            except Exception as e:
                logger.error(f"Error while fetching: {url} - {e}")
                return f"Error fetching content from: {url}"

        return await process_url(url)

    async def visit_urls_extract(
        self,
        rendered_html: str,
        max_num_links: int = MAX_NUM_LINKS,
        visited_links: VisitedLinks = visited_links,
    ) -> tuple[str, list]:
        """
        Extracts and visits links from rendered HTML.

        Args:
            rendered_html (str): The rendered HTML content.
            max_num_links (int, optional): The maximum number of links to visit. Defaults to MAX_NUM_LINKS.
            visited_links (VisitedLinks): Keeps track of the visited links (URLs used for information extraction).

        Returns:
            tuple: A tuple containing the extracted contents and the anchor tags.
                - The extracted contents as a string. If no contents are found, returns "Content not found".
                - The anchor tags as a list.

        """
        # get num tokens (prompt + chat history+query)
        self.internal_num_tokens = self.agent_executor.compute_internal_tokens(
            self.query
        )
        # Clear the list of visited links
        visited_links.clear()
        self.contents = []
        soup = BeautifulSoup(rendered_html, "html.parser")
        # 'gs-title' is the class attached to the anchor tag that contains the search result (University website search result page)
        self.anchor_tags = soup.find_all(
            "a", class_="gs-title"
        )  # the search result links

        async with aiohttp.ClientSession() as session:
            tasks = []

            # TODO Make sure that the search result links ordered is preserved (Implement test)
            for tag in self.anchor_tags:
                href = str(tag.get("href"))
                # Check for previously visited links
                if len(visited_links()) >= max_num_links:
                    break
                if href in visited_links():
                    continue

                visited_links().append(href)
                # Create and collect a task to fetch the URL
                tasks.append(self.fetch_url(session, href))

            with cache.detect as detector:
                # Gather the results of the tasks (text fetched from the URLs)
                self.contents = await asyncio.gather(*tasks, return_exceptions=True)
                if detector.calls:
                    logger.debug("Cache hit")

        # summarize the content if the total tokens exceed the limit
        # TODO this needs to be async and generate summary cached
        if self.contents:
            total_tokens, _ = self.compute_tokens("".join(self.contents))
            if total_tokens > settings.model.context_window:
                for i, text in enumerate(reversed(self.contents)):
                    original_index = len(self.contents) - i - 1
                    # start summarizing from the last text fetched (assumed to be the least important/relevant)
                    self.contents[original_index] = self.generate_summary(
                        text, self.query
                    )
                    # update the total tokens
                    total_tokens, _ = self.compute_tokens("".join(self.contents))
                    if total_tokens <= settings.model.context_window:
                        break

    def run(self, query: str) -> str:
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
            self.query = query
            query_url = decode_string(self.query)
            url = SEARCH_URL + query_url
            # TODO I/O operation (use async code) During waiting time compute the number of tokens in the prompt and chat history
            self.driver.get(url)
            rendered_html = self.driver.page_source

            asyncio.run(self.visit_urls_extract(rendered_html))

            final_output = "\n".join(self.contents)
            # for tesing
            # TODO REMOVE
            final_output_tokens, final_search_tokens = self.compute_tokens(final_output)
            logger.info(f"Search tokens: {final_search_tokens}")
            logger.info(f"Final output (search + prompt): {final_output_tokens}")
            # settings.final_output_tokens.append(final_output_tokens)
            # settings.final_search_tokens.append(final_search_tokens)

            return final_output if self.contents else self.no_content_found_message

        except Exception as e:
            logger.error(f"Error while searching the web: {e}", exc_info=True)
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
