import re
import urllib.parse
import logging

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


# TODO summarize  the content when it + the prompt +chat_history exceed the number of openai allow tokens (16385 tokens)
def summarise_content(text, question):
    print(
        "---------------------------------------------------------summarising content...---------------------------------------------------------"
    )
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
    summary_result_text = chain.run(input_documents=docs, question=question)
    # return chain.run(input_documents=docs, question=question)
    return summary_result_text


def decode_string(query):
    """
    Decode the query string to a format that can be used by the university website. e.g., wo+ist+der+universität
    :return: decoded string in this format: wo+ist+der+universität
    """

    # Regular expressions for checking different types of encoding
    utf8_pattern = re.compile(
        b"[\xc0-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf7][\x80-\xbf]{3}"
    )
    url_encoding_pattern = re.compile(r"%[0-9a-fA-F]{2}")
    unicode_escape_pattern = re.compile(r"\\u[0-9a-fA-F]{4}")

    # Check for UTF-8 encoding
    if utf8_pattern.search(query.encode("latin1")):
        try:
            decoded_utf8 = query.encode("latin1").decode("utf-8")
            logger.info(
                f"This is the query used by the University website: {decoded_utf8}"
            )

            return decoded_utf8.replace(" ", "+")
        except Exception as e:
            pass

    # Check for URL encoding
    if url_encoding_pattern.search(query):
        try:
            decoded_url = urllib.parse.unquote(query)
            logger.info(
                f"This is the query used by the University website: {decoded_url}"
            )

            return decoded_url.replace(" ", "+")
        except Exception as e:
            pass

    # Check for Unicode escape sequences
    if unicode_escape_pattern.search(query):
        try:
            decoded_unicode = query.encode("latin1").decode("unicode-escape")
            logger.info(
                f"This is the query used by the University website: {decoded_unicode}"
            )

            return decoded_unicode.replace(" ", "+")
        except Exception as e:
            pass

    query = query.replace(" ", "+")
    logger.info(f"This is the query used by the University website: {query}")

    return query  # Return the original string if no decoding is needed


def extract_and_visit_links(rendered_html: str, max_num_links: int = 2):
    """
    Extract the content from the search result  and visit the links to extract the content.
    :param rendered_html: The rendered HTML of the search result page (e.g., a set of links).
    :param max_num_links: The number of links to visit and extract the content from.
    """
    contents = []
    taken_from = "Information taken from:"
    search_result_text = "Content not found"
    visited_links = set()
    soup = BeautifulSoup(rendered_html, "html.parser")
    # 'gs-title' is the class of the anchor tag that contains the search result (University website search result page)
    anchor_tags = set(soup.find_all("a", class_="gs-title"))  # search result links
    for tag in anchor_tags:
        href = tag.get("href")
        response = requests.get(href)
        if response.status_code == 200:
            visited_links.add(href)
            # if the link is a pdf file
            if href.endswith(".pdf"):
                text = read_pdf_from_url(response)
                text = re.sub(
                    r"(\n\s*|\n\s+\n\s+)", "\n", text.strip()
                )  # remove extra spaces
                logger.info(f"Information extracted from pdf file: {href}")

            else:

                # TODO use the firefox driver to visit the link and extract the content
                link_soup = BeautifulSoup(response.content, "html.parser")
                # 'eb2' is the class of the div tag that contains the content of the search result (University website)
                div_content = link_soup.find("div", class_="eb2")
                if div_content:
                    text = re.sub(r"\n+", "\n", div_content.text.strip())

                    content_with_link = ""

                    for link in div_content.find_all("a", href=True):
                        text_anchor_tag = re.sub(
                            r"\n+", "\n", link.text.strip()
                        )  # Extract the text
                        content_with_link += f" - {text_anchor_tag}: {link['href']}"  # Combine the text and the link

                    text += "\nHref found in the text:\n" + content_with_link

                else:
                    contents.append(f"Failed to fetch content from the link: {href}")
                    print(f"Failed to fetch content from the link: {href}")

            text = f"{taken_from}{href}\n{text}"
            contents.append(text)

        # only visit the first two links
        if len(visited_links) >= max_num_links:
            break

    search_result_text = "\n".join(contents)

    return search_result_text


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
        # TODO need to check if the query is in German, if not then translate it to German
        query = query
        print(f"------Query--------: {query}")
        query_url = decode_string(query)
        print(f"------Query URL--------: {query_url}")
        # constructs the complete URL for the search
        firefox_options = Options()
        firefox_options.add_argument("--headless")  # Run Firefox in headless mode
        service = Service(SERVICE)  # path to the geckodriver
        driver = webdriver.Firefox(service=service, options=firefox_options)
        url = SEARCH_URL + query_url
        driver.get(url)
        rendered_html = driver.page_source

        search_result_text = extract_and_visit_links(rendered_html)
        logger.info(f"Length of the search result text: {len(search_result_text)}")
        # TODO use algorithm from my thesis to compute exact number of tokens given length of the search result text
        # truncate the search result text to 15000 tokens
        if len(search_result_text) > 15000:
            print(
                f"-------------------------------Truncate. length of the original search result text-------------------------: {len(search_result_text)}"
            )
            search_result_text = search_result_text[:15000]

        driver.quit()
        return search_result_text
    except Exception as e:
        logger.error(f"Error while searching the web: {e}")
        print(f"Error while searching the web: {e}")
        # raise ToolException('Error while searching the web')
        driver.quit()
        return "Error while searching the web"
