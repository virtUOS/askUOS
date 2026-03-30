import sys

sys.path.insert(0, "/app")
from time import sleep

import streamlit as st
from dotenv import load_dotenv
from streamlit import session_state

from ui.config.app_config import app_settings
from ui.utils.language import initialize_language
from ui.utils.utils import initialize_session_sate, load_css, setup_page

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
        start_message = app_settings.start_page.welcome_message_german
    else:
        start_message = app_settings.start_page.welcome_message_english

    st.markdown(
        start_message.format(
            app_settings.legal.data_protection,
            app_settings.legal.imprint,
        )
    )


def start_chat_button():
    with st.container(
        key="start-chat"
    ):  # do not change the key name, it is used in the CSS to style the button
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
