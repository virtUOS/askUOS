import streamlit as st
from streamlit import session_state
import src.config.settings as settings


class Language:
    """
    Sets the language used to create the agent executor.
    """

    _instance = None

    def set_language(self, language):
        self.language = language

    def __init_(self):
        raise RuntimeError("Call get_instance() instead")

    @classmethod
    def get_instance(cls, language="Deutsch"):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.set_language(language)
        return cls._instance


config_language = Language.get_instance()


def initialize_language():
    languages = {"Deutsch": "de", "English": "en"}

    def change_language():
        if session_state["selected_language"] == "English":
            set_language(language="en")
            config_language.set_language("English")

        else:
            session_state["selected_language"] = "Deutsch"
            set_language(language="de")
            config_language.set_language("Deutsch")

    # If no language is chosen yet set it to German
    if "selected_language" not in st.session_state or "lang" not in st.query_params:

        st.query_params["lang"] = "de"

    st.radio(
        "Language",
        options=languages,
        horizontal=True,
        key="selected_language",
        on_change=change_language,
        index=0,
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


# TODO DELETE THIS FUNCTION
def prompt_language():
    """
    Define the prompt text based on the selected language
    return: prompt_text, a dictionary containing the prompt text
    """

    if "selected_language" in st.session_state:
        if st.session_state["selected_language"] == "English":
            from src.chatbot.utils.prompt_text import prompt_text_english as prompt_text
        elif st.session_state["selected_language"] == "Deutsch":
            from src.chatbot.utils.prompt_text import prompt_text_deutsch as prompt_text
    else:
        from src.chatbot.utils.prompt_text import prompt_text_english as prompt_text

    return prompt_text
