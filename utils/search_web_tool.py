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
dotenv.load_dotenv()
from langchain_openai import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain_core.tools import ToolException
llm = ChatOpenAI(
    model="gpt-3.5-turbo-1106",
    temperature=0.3,
)




def summarise_content(content, query):
    print('---------------------------------------------------------summarising content...---------------------------------------------------------')
    llm = ChatOpenAI(temperature=0)
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n"], chunk_size=3500, chunk_overlap=300)
    docs = text_splitter.create_documents([content])

    reduce_template_string = """I will act as a text summarizer to help create a concise summary of the text provided, with a focus on addressing the given query. 
    The summary can be up to 12 sentences in length, capturing the key points and concepts from the original text without adding interpretations. The summary should keep the links found in the text. 
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
    return chain.run(input_documents=docs, question=query)



def extract_and_visit_links(html_code):
    contents = []
    visited_links = set()
    soup = BeautifulSoup(html_code, 'html.parser')
    anchor_tags = soup.find_all('a', class_='gs-title')
    for tag in anchor_tags:
        href = tag.get('href')
        if href not in visited_links:
            visited_links.add(href)
            response = requests.get(href)
            if response.status_code == 200:
                link_soup = BeautifulSoup(response.content, 'html.parser')
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
    if len(visited_links) ==2:
        search_result_text = visited_links[0]+'\n' + contents[0] + '\n\n' + visited_links[1] + '\n' + contents[1]
    elif len(visited_links) == 1:
        search_result_text = visited_links[0] + '\n' + contents[0]
    else:
        search_result_text = ''

    return search_result_text


def search_uni_web(query):
    # encode string into URL encoding
    try:
        query_url = urllib.parse.quote_plus(query)
        url = f"https://www.uni-osnabrueck.de/universitaet/organisation/zentrale-verwaltung/google-suche/?q={query_url}"

        firefox_options = Options()
        firefox_options.add_argument("--headless")  # Run Firefox in headless mode
        service = Service('/Users/yesidcano/Downloads/geckodriver')  # Replace with the actual path to geckodriver
        driver = webdriver.Firefox(service=service, options=firefox_options)

        driver.get(url)
        rendered_html = driver.page_source
        driver.quit()

        search_result_text = extract_and_visit_links(rendered_html)
        # if len(search_result_text) > 4000:
        #     summary_result_text = summarise_content(search_result_text, query)
        #     return summary_result_text
        # else:
        #
        #     return search_result_text
        return search_result_text

    except Exception as e:
        print('Error:', e)
        raise ToolException('Error while searching the web')

if __name__ == "__main__":
    query = 'Was kann ich an der Universität studieren?'
    rendered_html = search_uni_web(query)

    print()


