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


def prompt_language():
    '''
     Define the prompt text based on the selected language
     return: prompt_text, a dictionary containing the prompt text
    '''
   

    if "selected_language" in st.session_state:
        if st.session_state["selected_language"] == 'English':
            from utils.prompt_text import prompt_text_english as prompt_text
        elif st.session_state["selected_language"] == 'Deutsch':
            from utils.prompt_text import prompt_text_deutsch as prompt_text
    else:
        from utils.prompt_text import prompt_text_english as prompt_text
    
    return prompt_text