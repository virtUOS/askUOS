from time import sleep

import streamlit as st
from dotenv import load_dotenv
from streamlit import session_state

from pages.language import initialize_language
from pages.utils import initialize_session_sate, load_css, setup_page
from src.config.core_config import settings

# Load environment variables
load_dotenv()


# Initialization
def initialize_app():
    setup_page()
    load_css()
    initialize_session_sate()
    initialize_language()


def display_welcome_message():

    if st.session_state["chosen_language"] == "Deutsch":
        start_message = settings.start_page.welcome_message_german
    else:
        start_message = settings.start_page.welcome_message_english

    st.markdown(
        start_message.format(
            settings.legal.data_protection,
            settings.legal.imprint,
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
