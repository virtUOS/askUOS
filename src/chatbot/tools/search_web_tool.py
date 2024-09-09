import re
import urllib.parse

import dotenv
import requests
from bs4 import BeautifulSoup
from langchain.chains.summarize import load_summarize_chain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

from chatbot.utils.pdf_reader import read_pdf_from_url
from chatbot_log.chatbot_logger import logger
from config.settings import SEARCH_URL, SERVICE

dotenv.load_dotenv()


MAX_NUM_LINKS = 2
HEADLESS_OPTION = "--headless"
QUERY_SPACE_REPLACEMENT = "+"


# TODO summarize the content when it + the prompt +chat_history exceed the number of openai allowed tokens (16385 tokens)
def summarise_content(text, question):
    logger.info("Summarizing content...")
    llm = ChatOpenAI(temperature=0)

    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n"], chunk_size=3500, chunk_overlap=300
    )
    docs = text_splitter.create_documents([text])

    reduce_template_string = """I will act as a text summarizer to help create a concise summary of the text provided, with a focus on addressing the given query.
The summary can be up to 20 sentences in length, capturing the key points and concepts from the original text without adding interpretations. The summary should keep the links found in the text.
Irrelevant details not related to the question will be excluded from the summary.

Summarize this text:
{text}

question: {question}
Answer:
"""

    reduce_template = PromptTemplate(
        template=reduce_template_string, input_variables=["text", "question"]
    )
    chain = load_summarize_chain(
        llm=llm,
        chain_type="map_reduce",
        map_prompt=reduce_template,
        combine_prompt=reduce_template,
        verbose=True,
    )

    return chain.run(input_documents=docs, question=question)


def log_search_query(func):
    def wrapper(*args, **kwargs):
        query = func(*args, **kwargs)
        logger.info(f"This is the query used by the University website: {query}")
        return query

    return wrapper


@log_search_query
def decode_string(query):
    """
    Decode the query string to a format that can be used by the university website.
    """

    utf8_pattern = re.compile(
        b"[\xc0-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf7][\x80-\xbf]{3}"
    )
    url_encoding_pattern = re.compile(r"%[0-9a-fA-F]{2}")
    unicode_escape_pattern = re.compile(r"\\u[0-9a-fA-F]{4}")

    try:
        # Check for URL encoding
        if utf8_pattern.search(query.encode("latin1")):
            return (
                query.encode("latin1")
                .decode("utf-8")
                .replace(" ", QUERY_SPACE_REPLACEMENT)
            )
        if url_encoding_pattern.search(query):
            return urllib.parse.unquote(query).replace(" ", QUERY_SPACE_REPLACEMENT)
        if unicode_escape_pattern.search(query):
            return (
                query.encode("latin1")
                .decode("unicode-escape")
                .replace(" ", QUERY_SPACE_REPLACEMENT)
            )
    except Exception as e:
        logger.error(f"Error decoding query string: {e}")

    # return query  # Return the original string if no decoding is needed
    return query.replace(" ", QUERY_SPACE_REPLACEMENT)


def extract_pdf_text(href: str, response) -> str:

    text = read_pdf_from_url(response)
    return re.sub(r"(\n\s*|\n\s+\n\s+)", "\n", text.strip())


def extract_html_text(href: str, response) -> str:

    link_soup = BeautifulSoup(response.content, "html.parser")
    div_content = link_soup.find("div", class_="eb2")
    if div_content:
        text = re.sub(r"\n+", "\n", div_content.text.strip())
        content_with_link = ""
        for link in div_content.find_all("a", href=True):
            text_anchor_tag = re.sub(r"\n+", "\n", link.text.strip())
            content_with_link += f" - {text_anchor_tag}: {link['href']}"
        return text + "\nHref found in the text:\n" + content_with_link
    logger.error(f"Failed to fetch html content from: {href}")
    return ""


def extract_and_visit_links(rendered_html: str, max_num_links: int = MAX_NUM_LINKS):
    contents = []
    taken_from = "Information taken from:"
    search_result_text = "Content not found"
    visited_links = set()
    soup = BeautifulSoup(rendered_html, "html.parser")
    # 'gs-title' is the class attached to the anchor tag that contains the search result (University website search result page)
    anchor_tags = soup.find_all("a", class_="gs-title")  # the search result links
    # TODO Make sure that the search result links ordered is preserved (Implement test)
    for tag in anchor_tags:
        href = str(tag.get("href"))
        # there could be repeated links
        if href in visited_links:
            continue
        try:
            response = requests.get(href)
        except:
            logger.error(f"Error while fetching: {href}")
            continue

        if response.status_code == 200:

            if href.endswith(".pdf"):
                text = extract_pdf_text(href, response)
            else:
                text = extract_html_text(href, response)

            if text:
                text = f"{taken_from}{href}\n{text}"
                contents.append(text)
                visited_links.add(href)

                if len(visited_links) >= max_num_links:
                    break

    return "\n".join(contents) if contents else search_result_text


def search_uni_web(query: str) -> str:
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

        query_url = decode_string(query)
        logger.info(f"Decoded query URL: {query_url}")

        firefox_options = Options()
        firefox_options.add_argument(HEADLESS_OPTION)
        service = Service(SERVICE)
        driver = webdriver.Firefox(service=service, options=firefox_options)

        url = SEARCH_URL + query_url
        driver.get(url)
        rendered_html = driver.page_source
        search_result_text = extract_and_visit_links(rendered_html)

        # TODO use algorithm from my thesis to compute exact number of tokens given length of the search result text
        if len(search_result_text) > 15000:
            logger.info(
                f"Truncating search result text due to length: {len(search_result_text)}"
            )
            search_result_text = search_result_text[:15000]

        driver.quit()
        return search_result_text
    except Exception as e:
        logger.error(f"Error while searching the web: {e}", exc_info=True)
        driver.quit()
        return "Error while searching the web"


