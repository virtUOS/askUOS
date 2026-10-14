import re

import streamlit as st
from streamlit import session_state

from src.chatbot_log.chatbot_logger import logger
from ui.config.app_config import app_settings
from ui.config.models import IframePageInfo
from ui.utils.language import get_translator


def initialize_session_sate() -> None:
    """
    Initializes the session state with default values if they are not already set.
    """
    # Initialization
    defaults = {
        # Driven by ui_config.yml's configured `language` default, so a
        # university setting language: "English" actually sees English text
        # on first load instead of always getting German until the language
        # radio button is manually toggled.
        "_": get_translator(app_settings.language),
        "show_warning": True,
        "user_feedback_faces": None,
        "user_feedback_form": {},
        "user_query": None,  # use to log user query when user leaves feedback
        "feedback_saved": False,
        "response": None,  # use to log user query when user leaves feedback
        "time_taken": None,
        "chat_started": False,
        "selected_language": app_settings.language,
        "agent_language": app_settings.language,
        "agent": None,
        "ask_uos_user_id": None,
        "input_key_counter": 0,
        "visited_docs": None,
        "visited_links": None,
        "bot_called_from": None,
        # Set True right before generate_response starts streaming,
        # cleared in its own `finally` block -- which also fires the
        # backend cancel immediately, synchronously, if that block finds
        # the run was interrupted mid-generation (native chat_input stop
        # button, or any other widget click) rather than completed
        # normally. run() also checks this flag at the top of every script
        # run as a defensive fallback. See ChatApp.run()/generate_response
        # in ask_uos_chat.py.
        "is_generating": False,
    }

    for key, value in defaults.items():
        if key not in session_state:
            session_state[key] = value


def setup_page() -> None:
    """Set up the Streamlit page configuration."""
    st.set_page_config(
        page_title=app_settings.ui.page_title,
        page_icon=app_settings.ui.favicon_path,
        layout="centered",
        initial_sidebar_state="collapsed",
    )


def load_css() -> None:
    """Load custom CSS styles."""
    with open("/app/ui/static/css/style.css") as css:
        st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)


def bot_called_from() -> IframePageInfo | None:
    """
    Get the page from where the bot is called.
    """
    # --- Read the page context from query params ---
    try:
        page = st.query_params.get("page", "")
        page_title = st.query_params.get("title", "")
        if page or page_title:
            return IframePageInfo(page=page, page_title=page_title)
    except Exception as e:
        logger.error(
            f"[BOT-CALLED] Error while retrieving the page from where the bot was called: {e}"
        )

    return None


def _normalize_page(url: str) -> str:
    """Lowercase and drop scheme, leading "www." and trailing slashes."""
    url = re.sub(r"^https?://", "", url.strip().lower())
    return re.sub(r"^www\.", "", url).rstrip("/")


def get_page_text(field: str, default: str) -> str:
    """
    Return the text for ``field`` (e.g. "welcome_message_german") taking the
    ``page_overrides`` config into account.

    ``page`` (what the client sent) and each override's ``match`` are
    normalized (case, scheme, "www.", trailing slash). An override applies if
    its ``match`` equals the page or is a parent of it on a "/" boundary, so
    "sport.example.de" and "/sport" cover everything below them but "/sport"
    does not cover "/sportwissenschaft". Among applicable overrides that set
    ``field`` the longest ``match`` wins; otherwise ``default``.
    """
    if not app_settings.page_overrides:
        return default

    page_info = st.session_state.get("bot_called_from")
    page = _normalize_page((page_info.page if page_info else None) or "")
    if not page:
        return default

    best_len = -1
    text = default
    for override in app_settings.page_overrides:
        override_text = getattr(override, field, None)
        if not override_text:
            continue
        match = _normalize_page(override.match)
        if not match or (page != match and not page.startswith(match + "/")):
            continue
        if len(match) > best_len:
            best_len = len(match)
            text = override_text
    return text
