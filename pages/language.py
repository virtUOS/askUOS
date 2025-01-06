import streamlit as st
from streamlit import session_state
import gettext
from src.config.core_config import settings


def translate():
    """
    Translate text to German.
    return: The translation function using the German language.
    """
    de = gettext.translation("base", localedir="locale", languages=["de"])
    de.install()
    _ = de.gettext
    return _


def initialize_language() -> None:
    """
    Initializes the language selection for the application.

    This function sets up a radio button for language selection and handles
    the language change logic. It defaults to German if no language is chosen.

    The available languages are:
    - Deutsch (German)
    - English

    The function also updates the session state and configuration based on the
    selected language.
    """
    languages = {"Deutsch": "de", "English": "en"}

    def change_language():
        if session_state["selected_language"] == "English":
            set_language(language="en")
            settings.language = "English"
            session_state["_"] = gettext.gettext

        else:
            session_state["selected_language"] = "Deutsch"
            set_language(language="de")
            settings.language = "Deutsch"
            session_state["_"] = translate()

    # If no language is chosen yet set it to German
    if "selected_language" not in st.session_state or "lang" not in st.query_params:

        st.query_params["lang"] = "de"

    st.radio(
        "Language",
        options=languages,
        horizontal=True,
        key="selected_language",
        on_change=change_language,
        index=1 if settings.language == "English" else 0,
        label_visibility="hidden",
    )


def set_language(language) -> None:
    """
    Add the language to the query parameters based on the selected language.
    param language: The selected language.
    """
    if language == "en":
        st.query_params["lang"] = "en"
    elif language == "de":
        st.query_params["lang"] = "de"
