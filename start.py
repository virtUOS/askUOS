import streamlit as st
from time import sleep
from dotenv import load_dotenv
from streamlit import session_state

from src.config.core_config import settings
from pages.language import initialize_language
from pages.utils import initialize_session_sate, setup_page, load_css

# Load environment variables
load_dotenv()


# Initialization
def initialize_app():
    setup_page()
    initialize_session_sate()
    initialize_language()
    load_css()


def display_welcome_message():
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


def start_chat_button():
    with st.container(key="start-chat"):
        button_name = (
            session_state["_"]("Continue Chatting")
            if session_state.chat_started
            else session_state["_"]("Start Chatting")
        )

        if st.button(button_name, type="primary"):
            session_state.show_warning = False
            session_state.chat_started = True
            sleep(0.5)
            st.switch_page("pages/ask_uos_chat.py")


# Run the application
def main():
    initialize_app()
    display_welcome_message()
    start_chat_button()


if __name__ == "__main__":
    main()
