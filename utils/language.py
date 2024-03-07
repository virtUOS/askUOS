import streamlit as st
import gettext
from streamlit import session_state


def initialize_language():
    languages = {"English": "en", "Deutsch": "de"}

    def change_language():
        if session_state["selected_language"] == 'English':
            set_language(language='en')

        else:
            set_language(language='de')


    # If no language is chosen yet set it to German
    if 'selected_language' not in st.session_state or 'lang' not in st.query_params:

        st.query_params['lang'] = 'en'

    st.radio(
        "Language",
        options=languages,
        horizontal=True,
        key="selected_language",
        on_change=change_language,
        index=0,
        label_visibility='hidden'
    )





def set_language(language) -> None:
    """
    Add the language to the query parameters based on the selected language.
    param language: The selected language.
    """
    if language == 'en':
        st.query_params["lang"] = "en"
    elif language == 'de':
        st.query_params["lang"] = "de"
