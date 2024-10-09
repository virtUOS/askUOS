# streamlit run start.py

from time import sleep

import streamlit as st
from dotenv import load_dotenv
from streamlit import session_state

from pages.language import initialize_language
from pages.utils import initialize_session_sate

load_dotenv()


# Initialization
initialize_session_sate()


st.set_page_config(
    page_title="🤗💬 Campus Management Chatbot",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)


with open("./pages/static/style.css") as css:
    st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)

# st.markdown("![Click me](app/static/Icon-chatbot.png)")


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


initialize_language()

start_message = """
## Welcome to the Campus Management Chatbot.
### Our chatbot is designed to assist you with queries related to the University of Osnabrueck (e.g., applying or studying at the University).

- **This tool is a temporary test server meant for gathering feedback over a few days.**
- **It is intended for internal use only and not for public access.**
- With this test I am interested in finding out when the chat usually hallucinates and how often it hallucinates.
- I am also interested in getting a sense of how often the chatbot is able to provide the correct answer to the user's question.
Kindly note that any information you input or search for in the chat area is sent to OpenAI.
The Chatbot is powered by gpt-4o.

Have any question? Email me at yecanocastro@uos.de
"""


st.markdown(session_state["_"](start_message))


if st.button(session_state["_"]("Start Chatting"), type="primary"):

    sleep(0.5)
    st.switch_page("pages/streamlit_chat.py")
