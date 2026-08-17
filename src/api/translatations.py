import gettext
from functools import lru_cache

from src.config.core_config import settings
from src.config.models import Languages, MsgName


@lru_cache(maxsize=4)
def get_translator(language: str):
    """Return a gettext translation function for the given language."""
    lang_map = {"deutsch": "de", "english": "en"}
    lang_code = lang_map.get(language.lower(), "de")
    try:
        translation = gettext.translation(
            "base", localedir="locale", languages=[lang_code]
        )
        translation.install()
        return translation.gettext
    except FileNotFoundError:
        # Fallback: return identity function
        return lambda s: s


@lru_cache(maxsize=4)
def _get_error_messages(language: str) -> dict:
    """All user-facing error messages, translated."""
    _ = get_translator(language)
    further_help = ""
    if settings.parsed_messages:
        if settings.parsed_messages.get(MsgName.further_help.value, None):
            further_help = (
                settings.parsed_messages[MsgName.further_help.value]["german"]
                if language == Languages.GERMAN
                else settings.parsed_messages[MsgName.further_help.value]["english"]
            )
            further_help = f"\n\n{further_help}"

    return {
        "recursion": _(
            "I'm sorry, but I couldn't find enough information to fully answer your question. Could you please try rephrasing your query and ask again?"
        )
        + further_help,
        "search_error": _(
            "I'm sorry, something went wrong while connecting to the data provided. If the error persists, please reach out to the administrators for assistance."
        )
        + further_help,
        "generic": _(
            "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
        )
        + further_help,
        "generic_with_references": _(
            "I'm sorry, but I am unable to process your request right now. I've gathered some sources below that might be helpful. Feel free to take a look, or try asking your question in a different way."
        )
        + further_help,
    }
