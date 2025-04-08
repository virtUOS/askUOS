from typing import Optional, Union

import dotenv
from bs4 import BeautifulSoup
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter

from src.chatbot_log.chatbot_logger import logger

dotenv.load_dotenv()


def university_applications(user_input: str, **kwargs):

    instructions = """
     
    1. Visit the Online-Bewerbungsportal (online application portal) on the university's website.
    2. Review the application deadlines and requirements for your desired program.
    3. Complete the online application form and submit the required documents.
    4. Keep track of the application status and any additional steps required. For more detailed information, you can visit the university's website or contact the Persönliche Studienberatung (personal study advisory service).
     
    """

    # call web search

    return instructions
