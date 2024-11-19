import io
from PyPDF2 import PdfReader
import requests
import re
import concurrent.futures
from typing import Optional, Tuple


def read_pdf_from_url(pdf_bytes: bytes, num_pages: int = 7) -> str:
    """
    Read the content of a PDF file from a given byte stream.

    Args:
        pdf_bytes (bytes): Raw bytes of the PDF content.
        num_pages (int, optional): Number of pages to process. If None, process all pages. Defaults to 7.

    Returns:
        str: Extracted text content from the PDF.
    """

    pdf_stream = io.BytesIO(pdf_bytes)

    pdf_text = ""
    with pdf_stream as f:
        reader = PdfReader(f)
        if num_pages is None:
            num_pages = len(reader.pages)
        else:
            num_pages = min(num_pages, len(reader.pages))

        for page_num in range(num_pages):
            page = reader.pages[page_num]
            pdf_text += page.extract_text() or ""

    return pdf_text


# def open_pdf_as_binary(pdf_url: str):
#     try:
#         # Send a GET request to the URL to download the PDF file
#         response = requests.get(pdf_url)
#         response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes

#         # Return the binary content of the PDF file
#         return response.content
#     except requests.exceptions.RequestException as e:
#         print(f"Error: Failed to retrieve the PDF file from the URL: {e}")
#         return None


def extract_pdf_url(text: str):
    """
    Extracts the URL of a PDF file from the given text.

    Args:
        text (str): The text to search for PDF file URLs.

    Returns:
        tuple: A tuple containing the content of the PDF file (bytes) and the filename (str) if a PDF file is found,
               otherwise (None, None).
    """
    # Regular expression to detect links to PDF files
    pattern = r'(https?://[^/]+)?(/[^"]*\/([^"/]+\.pdf))'

    # Default domain
    default_domain = [
        "https://www.lili.uni-osnabrueck.de",
        "https://www.uni-osnabrueck.de",
    ]

    # Find all matches in the text
    matches = re.findall(pattern, text)

    if matches:
        # TODO if there are multiple PDF files in the response, choose the most relevant one based on the context
        for match in matches:
            domain, path, filename = match
            if domain is None:
                for d in default_domain:
                    response = requests.get(
                        d + path
                    )  # TODO dont i need the filename as well??
                    if response.status_code == 200:
                        break
                    else:
                        continue

            else:
                response = requests.get(
                    domain + path
                )  # TODO dont i need the filename as well??
    else:
        return None, None

    if response.status_code == 200:
        return response.content, filename
    else:
        return None, None


# Function to run the extract_pdf_url with a timeout
def extract_pdf_with_timeout(
    text: str, timeout: int
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Extracts PDF with a timeout.

    Args:
        text (str): The text (final answer) to extract PDF links from.
        timeout (int): The maximum time to wait for the extraction, in seconds.

    Returns:
        Tuple[Optional[bytes], Optional[str]]: A tuple containing the extracted PDF bytes
        and the URL of the extracted PDF. If the operation times out, returns (None, None).
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(extract_pdf_url, text)
        try:
            result = future.result(timeout=timeout)
            return result
        except concurrent.futures.TimeoutError:
            print(f"Operation timed out after {timeout} seconds")
            return None, None
