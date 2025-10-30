import asyncio
import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Literal, Optional, Tuple
from urllib.parse import unquote, urlparse

from crawl4ai import *
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tqdm.asyncio import tqdm

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


OUTPUT_DIR = "/app/data_ingestion/faqs_output_md"
MODEL_NAME = "google/gemma-3-27b-it"
TARGET_ELEMENTS = ["main", "div#content"]


class IsPageFAQ(BaseModel):
    is_faq: Literal["yes", "no"] = Field(
        description="Indicates whether the page is a FAQ page or not."
    )
    reason: str = Field(
        description="Reasoning behind the classification of the page as a FAQ or not."
    )


class FAQDetectorConfig:
    """Configuration class for FAQ detector."""

    def __init__(
        self,
        output_dir: str = OUTPUT_DIR,
        target_elements: List[str] = None,
        model_name: str = MODEL_NAME,
    ):
        self.output_dir = Path(output_dir)
        self.target_elements = target_elements or TARGET_ELEMENTS
        self.model_name = model_name

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)


class FAQDetector:
    """Main class for detecting FAQ pages from sitemap URLs."""

    def __init__(self, config: FAQDetectorConfig):
        self.config = config
        self._setup_crawler_config()
        self._setup_llm()
        self._setup_prompt()

    def _setup_crawler_config(self) -> None:
        """Setup crawler configuration."""
        self.browser_config = BrowserConfig(
            headless=True,
            verbose=True,
        )

        self.run_config = CrawlerRunConfig(
            cache_mode=CacheMode.DISABLED,
            target_elements=self.config.target_elements,
            scan_full_page=True,
            stream=False,
        )

    def _setup_llm(self) -> None:
        """Setup language model client."""
        self.client = ChatOpenAI(
            base_url=os.getenv("VLLM_BASE_URL"),
            api_key=os.getenv("VLLM"),
            model=self.config.model_name,
            temperature=0,
        )
        self.llm_structured_output = self.client.with_structured_output(IsPageFAQ)

    def _setup_prompt(self) -> None:
        """Setup the prompt template for FAQ classification."""
        self.prompt = PromptTemplate(
            template="""
            You are an evaluator determining whether the content of a web page qualifies as a Frequently Asked Questions (FAQ) page. 
            Follow these guidelines:

                1. A FAQ page typically contains a list of questions and their corresponding answers, often organized by topic.
                2. If the content is a list of questions and answers, it is an FAQ page.
                3. If the content **only mentions** or **references** an FAQ without providing a list of questions and answers, it is NOT  an FAQ page.
                4. If the content is a single question and answer, it is NOT an FAQ page.
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

    def extract_urls_from_txt_file(self, file_path: str) -> List[str]:
        """Extract URLs from a text file."""
        try:
            with open(file_path, "r") as f:
                urls = [line.strip() for line in f if line.strip()]
            logger.info(f"Extracted {len(urls)} URLs from text file")
            return urls
        except Exception as e:
            logger.error(f"Error extracting URLs from text file: {e}")
            return []

    def extract_urls_from_sitemap(self, sitemap_path: str) -> List[str]:
        """Extract URLs from a sitemap XML file."""
        try:
            tree = ET.parse(sitemap_path)
            root = tree.getroot()
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            urls = [loc.text for loc in root.findall(".//sm:loc", ns)]
            logger.info(f"Extracted {len(urls)} URLs from sitemap")
            return urls
        except Exception as e:
            logger.error(f"Error extracting URLs from sitemap: {e}")
            return []

    async def crawl_url(self, url: str) -> Optional[str]:
        """Crawl a single URL and return its content."""
        try:
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                result = await crawler.arun(url=url, config=self.run_config)
                return result
        except Exception as e:
            logger.error(f"Error crawling URL {url}: {e}")
            return None

    def save_faq_content(self, content: CrawlResult, url: str) -> None:
        """Save FAQ content to a Markdown file."""
        try:
            parsed = urlparse(url)
            path = unquote(parsed.path.lstrip("/"))
            if not path:
                path = "root"

            filename = path.rstrip("/").replace("/", "_")
            if not filename:
                filename = "root"

            output_file = self.config.output_dir / f"{filename}.md"

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(
                    f"""
---
title: "{content.metadata['title'] or 'FAQ Page'}"
url: "{url}"
---

### {content.metadata['title'] or 'FAQ Page'}. Source: {url}\n\n{content.markdown}
"""
                )

            logger.info(f"FAQ content saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving content for URL {url}: {e}")

    def classify_content(self, content: str) -> Optional[IsPageFAQ]:
        """Classify if the content is a FAQ page using LLM."""
        try:
            chain = self.prompt | self.llm_structured_output
            response = chain.invoke({"content": content})
            return response
        except Exception as e:
            logger.error(f"Error classifying content: {e}")
            return None

    def save_url_lists(
        self, faq_urls: List[str], not_faq_urls: List[str], failed_urls: List[str]
    ) -> None:
        """Save the categorized URL lists to files."""
        base_path = Path("/app/data_ingestion")

        if not_faq_urls:
            with open(base_path / "not_faq_urls_llm_judge.txt", "w") as f:
                f.write("\n".join(not_faq_urls))

        if faq_urls:
            with open(base_path / "faq_urls_judge_llm.txt", "w") as f:
                f.write("\n".join(faq_urls))

        if failed_urls:
            with open(base_path / "failed_urls.txt", "w") as f:
                f.write("\n".join(failed_urls))

    async def process_urls(
        self, url_source, url_source_path, classify_content
    ) -> Tuple[List[str], List[str], List[str]]:
        """Process all URLs from sitemap and classify them."""

        if url_source == "txt":
            urls = self.extract_urls_from_txt_file(url_source_path)
        else:
            urls = self.extract_urls_from_sitemap(url_source_path)
        if not urls:
            logger.warning("No URLs found in sitemap")
            return [], [], []

        faq_urls = []
        not_faq_urls = []
        failed_urls = []

        # Create progress bar
        progress_bar = tqdm(urls, desc="Processing URLs", unit="url", colour="green")

        for url in progress_bar:
            # Update progress bar description with current URL
            progress_bar.set_postfix_str(
                f"Current: {url[:50]}{'...' if len(url) > 50 else ''}"
            )

            # Crawl the URL
            content = await self.crawl_url(url)
            if content.markdown is None:
                failed_urls.append(url)
                progress_bar.set_postfix_str(
                    f"Failed: {url[:50]}{'...' if len(url) > 50 else ''}"
                )
                continue

            if classify_content:
                # Classify the content
                response = self.classify_content(content.markdown)
                if response is None:
                    failed_urls.append(url)
                    progress_bar.set_postfix_str(
                        f"Classification failed: {url[:50]}{'...' if len(url) > 50 else ''}"
                    )
                    continue

                # Categorize based on classification
                if response.is_faq.lower() == "yes":
                    faq_urls.append(url)
                    self.save_faq_content(content, url)
                    logger.info(f"FAQ page detected: {url}. Reason: {response.reason}")
                    progress_bar.set_postfix_str(
                        f"FAQ found: {url[:50]}{'...' if len(url) > 50 else ''}"
                    )
                else:
                    not_faq_urls.append(url)
                    progress_bar.set_postfix_str(
                        f"Not FAQ: {url[:50]}{'...' if len(url) > 50 else ''}"
                    )
            else:
                # If not classifying, just save all crawled content as FAQ
                faq_urls.append(url)
                self.save_faq_content(content, url)
                logger.info(f"FAQ page saved without classification: {url}")
                progress_bar.set_postfix_str(
                    f"Saved as FAQ: {url[:50]}{'...' if len(url) > 50 else ''}"
                )
        # Close progress bar
        progress_bar.close()

        return faq_urls, not_faq_urls, failed_urls

    async def run(
        self,
        url_source: Literal["sitemap", "txt"],
        url_source_path: str,
        save_results: bool = True,
        classify_content: bool = True,
    ) -> None:
        """Main method to run the FAQ detection process.
        Args:
            url_source: Source type, either 'sitemap' or 'txt'.
            url_source_path: Path to the sitemap XML file or text file with URLs.
            save_results: Whether to save the categorized URL lists to files.
            classify_content: Whether to classify content using LLM. If False, all crawled pages are saved as FAQ.
        """
        logger.info("Starting FAQ detection process")

        faq_urls, not_faq_urls, failed_urls = await self.process_urls(
            url_source, url_source_path, classify_content
        )

        if save_results:
            # Save results
            self.save_url_lists(faq_urls, not_faq_urls, failed_urls)

        # Log summary
        logger.info(f"FAQ detection completed:")
        logger.info(f"  - FAQ pages found: {len(faq_urls)}")
        logger.info(f"  - Non-FAQ pages: {len(not_faq_urls)}")
        logger.info(f"  - Failed to process: {len(failed_urls)}")

        if faq_urls:
            logger.info(f"FAQ URLs: {faq_urls}")
        if failed_urls:
            logger.info(f"Failed URLs: {failed_urls}")


async def export_single_faq_page_to_md(url: str) -> None:
    """Utility function to export a single FAQ page to Markdown."""
    config = FAQDetectorConfig()
    detector = FAQDetector(config)
    content = await detector.crawl_url(url)
    if content and content.markdown:
        detector.save_faq_content(content, url)
        logger.info(f"Successfully exported FAQ page to Markdown: {url}")
    else:
        logger.error(f"Failed to crawl or export FAQ page: {url}")


async def main():
    """Main function to run the FAQ detector."""
    config = FAQDetectorConfig()
    detector = FAQDetector(config)
    # url_source_path = "/app/data_ingestion/sitemap.xml"
    # url_source_path = "/app/data_ingestion/sitemap-uos-faq_AI_VERIFIED.xml"
    url_source = "txt"  # Change to "sitemap" to use sitemap.xml
    url_source_path = "/app/data_ingestion/faq_urls_judge_llm.txt"  # Path
    await detector.run(
        url_source, url_source_path, save_results=False, classify_content=False
    )  # change to True to save a report of the results. Set classify_content to False to skip LLM classification and save all crawled pages as FAQ.


if __name__ == "__main__":
    # export_single_faq_page_to_md("url_to_faq_page_here")
    asyncio.run(main())
