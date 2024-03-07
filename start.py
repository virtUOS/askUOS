# streamlit run start.py

import os
from time import sleep
from dotenv import load_dotenv
import streamlit as st
from streamlit import session_state
from utils.language import  initialize_language

load_dotenv()


st.set_page_config(page_title="🤗💬 Campus Management Chatbot", page_icon="🤖", layout="centered", initial_sidebar_state="collapsed")
st.markdown(
    """
<style>
    [data-testid="collapsedControl"] {
        display: none
    }
</style>
""",
    unsafe_allow_html=True,
)


start_message = """
## Welcome to the Campus Management Chatbot.
### This is a chatbot that can help you with questions about the University of Osnabrueck.

**This Tool should be used for testing purposes only.**

"""

if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == 'Deutsch':
        start_message = """
## Willkommen beim Campus Management Chatbot.
### Dies ist ein Chatbot, der Ihnen bei allen Fragen rund um die Universität Osnabrück helfen kann.

**Dieses Tool sollte nur zu Testzwecken verwendet werden.**
        """

initialize_language()





st.markdown(start_message)




if st.button("Start Chatting", type="primary"):

    sleep(0.5)
    st.switch_page("pages/streamlit_chat.py")


