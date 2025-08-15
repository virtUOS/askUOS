import asyncio
import os
from typing import Literal

import requests
from crawl4ai import *
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

SITE_MAP = "/app/data_ingestion/sitemap.xml"
OUTPUT_DIR = "/app/data_ingestion/faqs_output"


target_elements = ["main", "div#content"]

browser_config = BrowserConfig(
    headless=True,
    verbose=True,
)

run_config = CrawlerRunConfig(
    # cache_mode=CacheMode.ENABLED,
    cache_mode=CacheMode.DISABLED,
    target_elements=target_elements,
    scan_full_page=True,
    stream=False,
)


client = ChatOpenAI(
    base_url=os.getenv("VLLM_BASE_URL"),
    api_key=os.getenv("VLLM"),
    model="google/gemma-3-27b-it",
    temperature=0,
    streaming=True,
)


class IsPageFAQ(BaseModel):
    is_faq: Literal["yes", "no"] = Field(
        description="Indicates whether the page is a FAQ page or not. "
    )
    reason: str = Field(
        description="Reasoning behind the classification of the page as a FAQ or not."
    )


llm_structured_output = client.with_structured_output(IsPageFAQ)


prompt = PromptTemplate(
    template="""
        You are judge that assess if the content of web page is Frequently ask question FAQ page or not. 
        Follow these guidelines:

            1. A FAQ page typically contains a list of questions and their corresponding answers, often organized by topic.
            2. If the content is a list of questions and answers, it is an FAQ page.
            3. If the content **only mentions** or **references** an FAQ without providing a list of questions and answers, it is not an FAQ page.
            4. If the content is a single question and answer, it is not an FAQ page.
            5. If the content is a general information page without any questions and answers, it is not an FAQ page.
            6. If the content is a blog post or article that discusses a topic without a structured Q&A format, it is not an FAQ page.

        ### Evaluation Task:
        Determine if the content of the web page is a FAQ page or not based on the provided criteria. 
        - If it is a FAQ page, respond with "yes" and provide a brief reason.
        - If it is not a FAQ page, respond with "no" and provide a brief reason.
        
        Proceed with the evaluation based on these criteria.

        ### Web Page Content to be Evaluated:
        {content}
            """,
    input_variables=["content"],
)


async def run_crawler(url: str):

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=run_config,
        )

        return result


def classify_faq_page(urls_file: str):
    """Classify if the content is a FAQ page."""

    not_faq_urls = []
    page_is_faq = []
    judge_fail_urls = []
    with open(urls_file, "r") as file:
        urls = file.read().splitlines()

    for url in urls:

        res = asyncio.run(run_crawler(url))
        content = res.markdown

        chain = prompt | llm_structured_output

        try:
            response = chain.invoke(
                {
                    "content": content,
                }
            )
        except Exception as e:
            judge_fail_urls.append(url)
            print(f"Error occurred while processing {url}: {e}")
            continue

        if response.is_faq.lower() == "no":

            not_faq_urls.append(url)

        else:
            page_is_faq.append(url)
            # serve existing answer
            print(f"This url {url} is a FAQ page. Reason: {response.reason}")

    if not_faq_urls:
        with open("/app/data_ingestion/not_faq_urls_llm_judge.txt", "w") as file:
            for url in not_faq_urls:
                file.write(f"{url}\n")

    if page_is_faq:
        with open("/app/data_ingestion/faq_urls_judge_llm.txt", "w") as file:
            for url in page_is_faq:
                file.write(f"{url}\n")

    print(
        f"-----------------------------Finished processing URLs. Found {len(not_faq_urls)} non-FAQ pages. Urls: {not_faq_urls}"
    )

    if page_is_faq:
        print(
            f"---------------------------------------Found {len(page_is_faq)} FAQ pages. Urls: {page_is_faq}"
        )

    if judge_fail_urls:
        print(
            f"---------------------------------------Found {len(judge_fail_urls)} URLs that failed to process. Urls: {judge_fail_urls}"
        )

    print()


classify_faq_page("/app/data_ingestion/not_found_urls_scraper.txt")

# messages = [
#     (
#         "system",
#         "You are a helpful translator. Translate the user sentence to French.",
#     ),
#     ("human", "I love programming."),
# ]

# response = client.invoke(messages)

print()
