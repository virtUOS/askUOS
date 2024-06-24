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


def application_instructions (user_input: str, **kwargs):

    instructions = """
     
    1. Visit the Online-Bewerbungsportal (online application portal) on the university's website.
    2. Review the application deadlines and requirements for your desired program.
    3. Complete the online application form and submit the required documents.
    4. Keep track of the application status and any additional steps required. For more detailed information, you can visit the university's website or contact the Persönliche Studienberatung (personal study advisory service).
     
    """
    
    return instructions

