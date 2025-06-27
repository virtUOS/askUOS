import os
import re
import urllib.parse

from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from src.chatbot.utils.pdf_reader import read_pdf_from_url
from src.chatbot_log.chatbot_logger import logger

QUERY_SPACE_REPLACEMENT = "+"


def log_search_query(func):
    def wrapper(*args, **kwargs):
        query = func(*args, **kwargs)
        logger.info(f"Query used by the University website: {query}")
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


def extract_pdf_text(href: str, pdf_bytes: bytes) -> str:

    # TODO append url to the text
    text = read_pdf_from_url(pdf_bytes)
    return re.sub(r"(\n\s*|\n\s+\n\s+)", "\n", text.strip())


# TODO: CREATE OBJECT PER USER SESSION. SHOULD NOT BE A GLOBAL OBJECT. use __slots__ to reduce memory usage


class ReferenceRetriever:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ReferenceRetriever, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self.__dict__:
            self.docs_references = []

    def format_references(self):
        """
        Formats the references in a human-readable format.
        """
        references = {}

        for doc in self.docs_references:
            source = os.path.basename(doc["source"])
            if source not in references:
                references[source] = {doc["page"]}
            else:
                references[source].add(doc["page"])

        return references

    def clear(self):
        """
        Clears the list of visited documents.
        """
        self.docs_references = []

    def __call__(self):
        return self.docs_references


visited_docs = ReferenceRetriever()
# visited_links = VisitedLinks()
# do_not_visit_links = DoNotVisitLinks()
