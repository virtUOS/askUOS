import io
from PyPDF2 import PdfReader
import requests
import re

def read_pdf_from_url(response, num_pages=7):
        """
        Read the content of a pdf file from a given response object
        :param response: response object from the request
        :param num_pages: number of pages to process. If None, process all pages
        """
        pdf_stream = io.BytesIO(response.content)

        pdf_text = ''
        with pdf_stream as f:
            reader = PdfReader(f)
            if num_pages is None:
                num_pages = len(reader.pages)
            else:
                num_pages = min(num_pages, len(reader.pages))

            for page_num in range(num_pages):
                page = reader.pages[page_num]
                pdf_text += page.extract_text()

        return pdf_text



    

def open_pdf_as_binary(pdf_url: str):
    try:
        # Send a GET request to the URL to download the PDF file
        response = requests.get(pdf_url)
        response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
        
        # Return the binary content of the PDF file
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to retrieve the PDF file from the URL: {e}")
        return None


def extract_pdf_url(text: str ):
    # Define a regular expression pattern to match and extract a PDF URL
    pdf_url_pattern = r'\b(https?://\S+\.pdf)\b'

    # Use re.search to find the pattern in the text
    match = re.search(pdf_url_pattern, text, re.IGNORECASE)
    if match:
        pdf_url = match.group(1)  # Extracted PDF URL
        pdf_filename = pdf_url.split("/")[-1]  # Extracted PDF file name from the URL
        return pdf_url, pdf_filename
    else:
        return None, None  # Return None for both URL and filename if no PDF URL is found