import csv
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def extract_urls_from_sitemap(xml_file):
    """Extract URLs from a sitemap XML file."""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        # The namespace in your XML
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [loc.text for loc in root.findall(".//sm:loc", ns)]
        return urls
    except Exception as e:
        logging.error(f"Error extracting URLs from sitemap: {e}")
        return []


def extract_faq_from_html(html_content):
    """
    Extract FAQ content from HTML with mixed content.
    Returns a list of tuples (question, answer)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    faq_pairs = []

    # Expanded patterns for FAQ identification in English and German
    faq_patterns = [
        r"FAQ",
        r"F-A-Q",
        r"Frequently Asked Questions",
        r"Common Questions",
        r"Questions and Answers",
        r"Q&A",
        r"Häufig gestellte Fragen",
        r"Fragen und Antworten",
        r"Häufige Fragen",
        r"Oft gestellte Fragen",
        r"Fragen & Antworten",
        r"F\.A\.Q",
        r"FAQs",
        r"Antworten auf häufige Fragen",
        r"Typische Fragen",
        r"Fragenkatalog",
        r"Fragenbeantwortung",
    ]

    faq_pattern = "|".join(faq_patterns)

    # Look for FAQ headings in both German and English
    faq_headings = soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6"],
        string=lambda s: s and re.search(faq_pattern, s, re.IGNORECASE),
    )

    if not faq_headings:
        logging.info(f"No FAQ headings found")
        return faq_pairs

    # --- Custom extraction for m-accordion__item ---
    accordion_items = soup.find_all("div", class_="m-accordion__item")
    for item in accordion_items:
        # Extract question from m-accordion__headline
        headline = item.find(class_="m-accordion__headline")
        question = None
        if headline:
            # The question is usually inside a <button> or directly as text
            button = headline.find("button")
            if button:
                question = button.get_text(strip=True)
            else:
                question = headline.get_text(strip=True)
        # Extract answer from m-accordion__itemBody > .content-element-text
        answer = ""
        body = item.find("div", class_="m-accordion__itemBody")
        if body:
            # Find all content-element-text blocks inside the body
            text_blocks = body.find_all("div", class_="content-element-text")
            answer_parts = []
            for block in text_blocks:
                # Extract all text (no HTML, no links)
                text = block.get_text(separator=" ", strip=True)
                if text:
                    answer_parts.append(text)
            answer = " ".join(answer_parts).strip()
        if question and answer:
            faq_pairs.append((question, answer))

    return faq_pairs


def save_to_csv(faq_pairs, output_file):
    """Save FAQ pairs to a tab-delimited CSV file"""
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile, delimiter="\t")
        writer.writerow(["Frage", "Antwort"])
        for question, answer in faq_pairs:
            writer.writerow([question, answer])
    logging.info(f"Saved {len(faq_pairs)} FAQ pairs to {output_file}")


def extract_faq_from_file(input_file, output_file):
    """Extract FAQs from an HTML file and save to CSV"""
    with open(input_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    faq_pairs = extract_faq_from_html(html_content)
    if faq_pairs:

        save_to_csv(faq_pairs, output_file)

    return len(faq_pairs)


def extract_faq_from_url(url, output_dir):
    """Extract FAQs from a URL and save to CSV, naming file after URL path"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        faq_pairs = extract_faq_from_html(response.text)
        if faq_pairs:
            # Name file after everything after the domain name
            parsed = urlparse(url)
            path = unquote(parsed.path.lstrip("/"))
            if not path:
                path = "root"
            # Remove trailing slash and replace slashes with underscores
            filename = path.rstrip("/").replace("/", "_")
            if not filename:
                filename = "root"
            output_file = os.path.join(output_dir, f"{filename}.csv")
            save_to_csv(faq_pairs, output_file)
        else:
            output_file = None
        return len(faq_pairs)
    except Exception as e:
        logging.error(f"Error fetching or processing URL: {e}")
        return 0


def process_sitemap(sitemap_path, output_dir):
    """Process all URLs from a sitemap and extract FAQs"""
    urls = extract_urls_from_sitemap(sitemap_path)
    not_found_urls = []
    if not urls:
        logging.error(f"No URLs found in {sitemap_path}")
        return

    os.makedirs(output_dir, exist_ok=True)

    total_faqs = 0
    for url in urls:
        count = extract_faq_from_url(url, output_dir)
        if count > 0:
            logging.info(f"Extracted {count} FAQs from {url}")
            total_faqs += count
        else:
            not_found_urls.append(url)
            # Remove empty files if any were created
            parsed = urlparse(url)
            path = unquote(parsed.path.lstrip("/"))
            if not path:
                path = "root"
            filename = path.rstrip("/").replace("/", "_")
            if not filename:
                filename = "root"
            output_file = os.path.join(output_dir, f"{filename}.csv")
            if os.path.exists(output_file):
                os.remove(output_file)
            logging.info(f"No FAQs found at {url}, file {output_file} removed.")

    logging.info(f"Extraction complete. Total FAQs found: {total_faqs}")
    return not_found_urls


def main():

    sitemap_path = "/app/data_ingestion/sitemap.xml"
    output_dir = "/app/data_ingestion/faqs_output"
    not_found_urls = process_sitemap(sitemap_path, output_dir)
    if not_found_urls:
        with open("/app/data_ingestion/not_found_urls.txt", "w") as f:
            for url in not_found_urls:
                f.write(url + "\n")


if __name__ == "__main__":
    main()


"""extract the faq content of this page. DO NOT add anything to the content, DO NOT summarize, keep the original laguage. Provide the result in csv format that match this requirement: If a file is in CSV/TXT format, it must be UTF-8 encoded with TAB as the delimiter to separate questions"""
