import re
import urllib.parse
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import requests
from bs4 import BeautifulSoup
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from PyPDF2 import PdfReader
import io
import dotenv

dotenv.load_dotenv()
from settings import SERVICE
from langchain_openai import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain_core.tools import ToolException

llm = ChatOpenAI(
    model="gpt-3.5-turbo-1106",
    temperature=0.3,
)


# todo summarize  the content when it + the prompt +chat_history exceed the number of openai allow tokens (16385 tokens)
def summarise_content(text, question):
    print(
        '---------------------------------------------------------summarising content...---------------------------------------------------------')
    llm = ChatOpenAI(temperature=0)
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n"], chunk_size=3500, chunk_overlap=300)
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
        template=reduce_template_string, input_variables=["text", "question"])
    chain = load_summarize_chain(
        llm=llm,
        chain_type='map_reduce',
        map_prompt=reduce_template,
        combine_prompt=reduce_template,
        verbose=True
    )
    summary_result_text = chain.run(input_documents=docs, question=question)
    # return chain.run(input_documents=docs, question=question)
    return summary_result_text

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

def extract_and_visit_links(html_code):
    contents = []
    visited_links = set()
    soup = BeautifulSoup(html_code, 'html.parser')
    # 'gs-title' is the class of the anchor tag that contains the search result (University website search result page)
    anchor_tags = soup.find_all('a', class_='gs-title')
    for tag in anchor_tags:
        href = tag.get('href')
        if href not in visited_links:
            visited_links.add(href)
            response = requests.get(href)
            if response.status_code == 200:
                # if the link is a pdf file
                if href.endswith('.pdf'):
                    text = read_pdf_from_url(response)
                    text = re.sub(r'(\n\s*|\n\s+\n\s+)', '\n', text.strip()) # remove extra spaces
                    contents.append(text)
                    print(f'Information extracted from pdf file: {href}')
                else:

                    link_soup = BeautifulSoup(response.content, 'html.parser')
                    # 'eb2' is the class of the div tag that contains the content of the search result (University website)
                    div_content = link_soup.find('div', class_='eb2')
                    if div_content:
                        text = re.sub(r'\n+', '\n', div_content.text.strip())
                        contents.append(text)
                    else:
                        contents.append('Content not found')
            else:
                contents.append('Failed to fetch content')
        
        # only visit the first two links
        if len(visited_links) == 1:
            break
    # todo search result needs to be summerized. There is a limitation from the OpenAI end to receive only 4000 tokens in the request.
    visited_links = list(visited_links)
    # append the link where the information was found, so that the AI can use as a reference when answering the question.
    taken_from = 'Information taken from:  '
    if len(visited_links) == 2:
        search_result_text = taken_from + visited_links[0] + '\n' + contents[0] + '\n\n' + taken_from + visited_links[
            1] + '\n' + contents[1]
    elif len(visited_links) == 1:
        search_result_text = taken_from + visited_links[0] + '\n' + contents[0]
    else:
        search_result_text = ''

    return search_result_text


def decode_string(query):
    """
    Decode the query string to a format that can be used by the university website. Ex. wo+ist+der+universität
    :param query: string to be decoded
    :return: decoded string in this format: wo+ist+der+universität
    """

    # Regular expressions for checking different types of encoding
    utf8_pattern = re.compile(b'[\xc0-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf7][\x80-\xbf]{3}')
    url_encoding_pattern = re.compile(r'%[0-9a-fA-F]{2}')
    unicode_escape_pattern = re.compile(r'\\u[0-9a-fA-F]{4}')

    # Check for UTF-8 encoding
    if utf8_pattern.search(query.encode('latin1')):
        try:
            decoded_utf8 = query.encode('latin1').decode('utf-8')
            print(f'This is the query used by the University website: {decoded_utf8}')
            return decoded_utf8.replace(' ', '+')
        except Exception as e:
            pass

    # Check for URL encoding
    if url_encoding_pattern.search(query):
        try:
            decoded_url = urllib.parse.unquote(query)
            print(f'This is the query used by the University website: {decoded_url}')
            return decoded_url.replace(' ', '+')
        except Exception as e:
            pass

    # Check for Unicode escape sequences
    if unicode_escape_pattern.search(query):
        try:
            decoded_unicode = query.encode('latin1').decode('unicode-escape')
            print(f'This is the query used by the University website: {decoded_unicode}')
            return decoded_unicode.replace(' ', '+')
        except Exception as e:
            pass

    query = query.replace(' ', '+')
    print(f'This is the query used by the University website: {query}')

    return query  # Return the original string if no decoding is needed


def search_uni_web(query):
    # encode string into URL encoding
    try:

        # query_url = urllib.parse.quote_plus(query)
        # todo need to check if the query is in german, if not then translate it to german
        query_url = decode_string(query)

        url = f"https://www.uni-osnabrueck.de/universitaet/organisation/zentrale-verwaltung/google-suche/?q={query_url}"

        firefox_options = Options()
        firefox_options.add_argument("--headless")  # Run Firefox in headless mode
        service = Service(SERVICE)  # Replace with the actual path to geckodriver
        driver = webdriver.Firefox(service=service, options=firefox_options)

        driver.get(url)
        rendered_html = driver.page_source
        driver.quit()

        search_result_text = extract_and_visit_links(rendered_html)
        # todo use algorithm form my thesis to compute exact number of tokens given length of the search result text
        # if len(search_result_text) > 15000:
        #     summary_result_text = summarise_content(search_result_text, query)
        #     print(
        #         f'-------------------------------length of the search result text (summary_result_text)-------------------------: {len(summary_result_text)}')
        #     return summary_result_text
        # else:
        #     print(
        #         f'-------------------------------length of the search result text-------------------------: {len(search_result_text)}')
        #     return search_result_text

        # truncate the search result text to 15000 tokens
        if len(search_result_text) > 15000:
            print(f'-------------------------------Truncate. length of the original search result text-------------------------: {len(search_result_text)}')
            search_result_text = search_result_text[:15000]
        print(
                f'-------------------------------length of the search result text-------------------------: {len(search_result_text)}')
        return search_result_text




        # return search_result_text

    except Exception as e:
        print('Error:', e)
        raise ToolException('Error while searching the web')


if __name__ == "__main__":
    query = 'Was kann ich an der Universität studieren?'
    rendered_html = search_uni_web(query)

    print()
