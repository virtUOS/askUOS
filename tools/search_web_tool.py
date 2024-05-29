from typing import Optional, Union
import re
import urllib.parse
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import requests
from bs4 import BeautifulSoup
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
import dotenv
from chatbot_log.chatbot_logger import logger
from utils.pdf_reader import read_pdf_from_url
import os
from langchain_openai import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain_core.tools import ToolException
from settings import SEARCH_URL
from urllib.parse import urljoin

dotenv.load_dotenv()



# TODO summarize  the content when it + the prompt +chat_history exceed the number of openai allow tokens (16385 tokens)
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



class DecodeStringMixin:
 
 def decode_string(self):
    """
    Decode the query string to a format that can be used by the university website. e.g., wo+ist+der+universität
    :return: decoded string in this format: wo+ist+der+universität
    """

    # Regular expressions for checking different types of encoding
    utf8_pattern = re.compile(b'[\xc0-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf7][\x80-\xbf]{3}')
    url_encoding_pattern = re.compile(r'%[0-9a-fA-F]{2}')
    unicode_escape_pattern = re.compile(r'\\u[0-9a-fA-F]{4}')

    # Check for UTF-8 encoding
    if utf8_pattern.search(self.query.encode('latin1')):
        try:
            decoded_utf8 = self.query.encode('latin1').decode('utf-8')
            logger.info(f'This is the query used by the University website: {decoded_utf8}')
           
            return decoded_utf8.replace(' ', '+')
        except Exception as e:
            pass

    # Check for URL encoding
    if url_encoding_pattern.search(self.query):
        try:
            decoded_url = urllib.parse.unquote(self.query)
            logger.info(f'This is the query used by the University website: {decoded_url}')
           
            return decoded_url.replace(' ', '+')
        except Exception as e:
            pass

    # Check for Unicode escape sequences
    if unicode_escape_pattern.search(self.query):
        try:
            decoded_unicode = self.query.encode('latin1').decode('unicode-escape')
            logger.info(f'This is the query used by the University website: {decoded_unicode}')
         
            return decoded_unicode.replace(' ', '+')
        except Exception as e:
            pass

    query = self.query.replace(' ', '+')
    logger.info(f'This is the query used by the University website: {query}')


    return query  # Return the original string if no decoding is needed


class ExtractAndVisitLinksMixin:

    def extract_and_visit_links(self):
        contents = []
        visited_links = set()
        soup = BeautifulSoup(self.rendered_html, 'html.parser')
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
                        logger.info(f'Information extracted from pdf file: {href}')
                        
                    else:

                        link_soup = BeautifulSoup(response.content, 'html.parser')
                        # 'eb2' is the class of the div tag that contains the content of the search result (University website)
                        div_content = link_soup.find('div', class_='eb2')
                        if div_content:
                            text = re.sub(r'\n+', '\n', div_content.text.strip())
                            
                            content_with_link = ''
                            # TODO FIX THE BASE URL AS IT CAN CHANGE
                            base_url = 'https://www.lili.uni-osnabrueck.de'
                            for link in div_content.find_all('a', href=True):
                                text = re.sub(r'\n+', '\n', link.text.strip())  # Extract the text
                                url = urljoin(base_url, link['href'])  # Resolve the relative URL to absolute
                                content_with_link += f" - {text}: {url}"  # Combine the text and the link
                            
                            text += 'Links found in the text:  ' + content_with_link
                            
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
    



class SearchUniWeb(DecodeStringMixin, ExtractAndVisitLinksMixin):

    '''
    Useful when the user asks questions about the University of Osnabrück. For example questions about 
    the application process or studying at the university in general. This tool is also useful to access updated application dates
    and updated dates and contact information. To use this tool successfully, take into account the previous interactions with the user (chat history) and the context of the conversation.
    '''


    def __init__(self, service_path:str):

        # path to the geckodriver
        self._service_path = service_path

        @property
        def service_path(self):
            return self._service_path
        
        @service_path.setter
        def service_path(self, value):
            # TODO check that the geckodriver is not corrupted
            if os.path.exists(value):
                self._service_path = value

            else:
                raise ValueError('The path to the geckodriver is not correct')
            
        self.firefox_options = Options()
        self.firefox_options.add_argument("--headless")  # Run Firefox in headless mode
        self.service = Service(self._service_path)  
        
            

    @classmethod
    def run(cls,service_path:str):
       
        return cls(service_path)
    
    def __call__(self, query):

        try:

            # query_url = urllib.parse.quote_plus(query)
            # todo need to check if the query is in german, if not then translate it to german
            self.query = query
            print(f'------Query--------: {self.query}')
            query_url = self.decode_string()
            
            print(f'------Query URL--------: {query_url}')
            
            # constructs the complete URL for the search
            url = SEARCH_URL + query_url
        
            driver = webdriver.Firefox(service=self.service, options=self.firefox_options)

            driver.get(url)
            self.rendered_html = driver.page_source
            driver.quit()

            search_result_text = self.extract_and_visit_links()
            logger.info(f'Length of the search result text: {len(search_result_text)}')
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
            logger.error(f'Error while searching the web: {e}')
            # raise ToolException('Error while searching the web')
            return 'Error while searching the web'
    
