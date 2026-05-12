import streamlit as st
from streamlit import session_state
from src.chatbot_log.chatbot_logger import logger
from ui.config.app_config import app_settings
from ui.utils.language import translate
from ui.config.models import IframePageInfo


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
    }

    for key, value in defaults.items():
        if key not in session_state:
            session_state[key] = value


def setup_page() -> None:
    """Set up the Streamlit page configuration."""
    st.set_page_config(
        page_title=app_settings.ui.page_title,
        page_icon="/app/ui/static/icons/Icon-chatbot.png",
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
            logger.info(
                f"[BOT-CALLED] The bot was called from {page}, page title: {page_title}"
            )
            return IframePageInfo(page=page, page_title=page_title)
    except Exception as e:
        logger.error(
            f"[BOT-CALLED] Error while retrieving the page from where the bot was called: {e}"
        )

    return None
