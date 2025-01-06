# streamlit run start.py

from time import sleep

import streamlit as st
from dotenv import load_dotenv
from streamlit import session_state
from src.config.core_config import settings
from pages.language import initialize_language
from pages.utils import initialize_session_sate

load_dotenv()


# Initialization
initialize_session_sate()


st.set_page_config(
    page_title="Ask.UOS",
    page_icon="app/static/Icon-chatbot.png",
    layout="centered",
    initial_sidebar_state="collapsed",
)


with open("./pages/static/style.css") as css:
    st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)


initialize_language()

start_message = """
## Welcome to Ask.UOS!
### Ask.UOS is a chatbot powered by OpenAI's GPT-4. 
### We are excited to assist you with this first experimental release! 

We take precautions to ensure a low rate of inaccurate answers. However, for your safety and to ensure the reliability of any information you receive, we recommend using human oversight in your decision-making processes, as this helps confirm that the information is safe, accurate, and appropriate for your needs.
If you're ever unsure about an answer, please check the provided sources.

Please note that the University of Osnabrück cannot be held liable for any actions, losses, or damages that may arise from the use of the chatbot. 

If you're interested, please follow the links to find more information about our [data protection policies]({}) and [imprint]({}).
"""

translated_start_message = session_state["_"](start_message)

st.markdown(
    translated_start_message.format(
        settings.legal.data_protection, settings.legal.imprint
    )
)


with st.container(
    key="start-chat"
):  # the key is used to identify the container in the page with the class st-key-start
    if session_state.chat_started:
        button_name = session_state["_"]("Continue Chatting")
    else:
        button_name = session_state["_"]("Start Chatting")

    if st.button(button_name, type="primary"):
        session_state.show_warning = False
        session_state.chat_started = True
        sleep(0.5)
        st.switch_page("pages/ask_uos_chat.py")
