import io
from PyPDF2 import PdfReader

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