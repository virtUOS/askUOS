import streamlit as st
from streamlit import session_state

from pages.language import translate
from src.config.core_config import settings


def initialize_session_sate() -> None:
    """
    Initializes the session state with default values if they are not already set.
    """
    # Initialization
    defaults = {
        "_": translate(),
        "show_warning": True,
        "user_feedback_faces": None,
        "user_feedback_form": {},
        "user_query": None,
        "feedback_saved": False,
        "response": None,
        "time_taken": None,
        "chat_started": False,
        "selected_language": settings.language,
    }

    for key, value in defaults.items():
        if key not in session_state:
            session_state[key] = value


def setup_page() -> None:
    """Set up the Streamlit page configuration."""
    st.set_page_config(
        page_title="ask.UOS",
        page_icon="app/static/Icon-chatbot.png",
        layout="centered",
        initial_sidebar_state="collapsed",
    )


def load_css() -> None:
    """Load custom CSS styles."""
    with open("./pages/static/style.css") as css:
        st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)
