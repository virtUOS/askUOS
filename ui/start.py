import sys

sys.path.insert(0, "/app")
from time import sleep

import streamlit as st
from dotenv import load_dotenv
from streamlit import session_state

from ui.config.app_config import app_settings
from ui.utils.language import initialize_language
from ui.utils.utils import (
    bot_called_from,
    get_page_text,
    initialize_session_sate,
    load_css,
    setup_page,
)

# Load environment variables
load_dotenv()


# Initialization
def initialize_app():
    setup_page()
    load_css()
    initialize_session_sate()
    initialize_language()
    # Capture page/title here too (not just on the chat page): a visitor's
    # very first chat-open lands on this disclaimer page, and st.switch_page
    # (in start_chat_button, below) drops the URL's query string on the way
    # to pages/ask_uos_chat.py -- capturing it here, into session_state that
    # persists across that switch, is what lets ask_uos_chat.py's own
    # bot_called_from() fallback find it even though its own URL is empty.
    fresh_page_info = bot_called_from()
    if fresh_page_info is not None:
        st.session_state["bot_called_from"] = fresh_page_info


def display_welcome_message():

    if st.session_state["chosen_language"] == "Deutsch":
        start_message = get_page_text(
            "welcome_message_german", app_settings.start_page.welcome_message_german
        )
    else:
        start_message = get_page_text(
            "welcome_message_english", app_settings.start_page.welcome_message_english
        )

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
