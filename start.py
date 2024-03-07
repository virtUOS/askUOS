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
### Our chatbot is designed to assist you with queries related to the University of Osnabrueck (e.g., applying or studying at the University).

- **This tool is a temporary test server meant for gathering feedback over a few days.**
- **It is intended for internal use only and not for public access.**
- The German version is still in progress and may not provide results as accurate as the English version (I suggest that you first use the English version).
- With this test I am interested in finding out when the chat usually hallucinates and how often it hallucinates.
- I am also interested in getting a sense of how often the chatbot is able to provide the correct answer to the user's question.

Kindly note that any information you input or search for in the chat area is sent to OpenAI.
The Chatbot is powered by gpt-3.5-turbo-1106.
"""

if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == 'Deutsch':
        start_message = """
## Willkommen beim Campus Management Chatbot.
### Unser Chatbot soll Ihnen bei Fragen rund um die Universität Osnabrück helfen (z.B. bei der Bewerbung oder dem Studium).

- Bei diesem Tool handelt es sich um einen temporären Testserver, mit dem wir über einige Tage hinweg Feedback einholen können.
- **Es ist nur für den internen Gebrauch und nicht für den öffentlichen Zugang bestimmt.**
- **Die deutsche Version ist noch in Arbeit und liefert möglicherweise nicht so genaue Ergebnisse wie die englische Version (ich empfehle, zunächst die englische Version zu verwenden).**
- Mit diesem Test möchte ich herausfinden, wann der Chat normalerweise halluziniert und wie oft er halluziniert.
- Ich bin auch daran interessiert, ein Gefühl dafür zu bekommen, wie oft der Chatbot in der Lage ist, die richtige Antwort auf die Frage des Benutzers zu geben.

Bitte beachten Sie, dass alle Informationen, die Sie in den Chatbereich eingeben oder nach denen Sie suchen, an OpenAI gesendet werden.
Der Chatbot wird von gpt-3.5-turbo-1106 betrieben.
"""

initialize_language()





st.markdown(start_message)




if st.button("Start Chatting", type="primary"):

    sleep(0.5)
    st.switch_page("pages/streamlit_chat.py")


