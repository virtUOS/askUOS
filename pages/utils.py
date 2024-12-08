from pages.language import translate
from streamlit import session_state


def initialize_session_sate() -> None:
    """
    Initializes the session state with default values if they are not already set.
    """
    # Initialization
    defaults = {
        "_": translate(),
        "selected_language": "Deutsch",
        "show_warning": True,
        "user_feedback": None,
        "user_query": None,
        "response": None,
        "time_taken": None,
    }

    for key, value in defaults.items():
        if key not in session_state:
            session_state[key] = value
