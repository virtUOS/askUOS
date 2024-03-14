from langchain_core.prompts import SystemMessagePromptTemplate
from langchain.prompts.prompt import PromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
import streamlit as st

# Define the prompt text based on the selected language
if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == 'English':
        from utils.prompt_text import prompt_text_english as prompt_text
    elif st.session_state["selected_language"] == 'Deutsch':
        from utils.prompt_text import prompt_text_deutsch as prompt_text
else:
    from utils.prompt_text import prompt_text_english as prompt_text


template_messages = [
    SystemMessagePromptTemplate(prompt=PromptTemplate(input_variables=['input', 'chat_history', 'agent_scratchpad'],
                                                      template=prompt_text['system_message'])),
    MessagesPlaceholder(variable_name='chat_history', optional=True),
    HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['input'], template='{input}')),
    MessagesPlaceholder(variable_name='agent_scratchpad')]

prompt = ChatPromptTemplate.from_messages(template_messages)


# print(f'------------------------------SystemMessagePromptTemplate: {prompt}')
