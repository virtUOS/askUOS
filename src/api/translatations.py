import gettext
from functools import lru_cache
from typing import Optional

from src.config.core_config import settings
from src.config.models import Languages, MsgName
from src.page_match import best_page_match


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
def _get_base_messages(language: str) -> dict:
    """All user-facing error messages, translated, without the further-help suffix."""
    _ = get_translator(language)
    return {
        "recursion": _(
            "I'm sorry, but I couldn't find enough information to fully answer your question. Could you please try rephrasing your query and ask again?"
        ),
        "search_error": _(
            "I'm sorry, something went wrong while connecting to the data provided. If the error persists, please reach out to the administrators for assistance."
        ),
        "generic": _(
            "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
        ),
        "generic_with_references": _(
            "I'm sorry, but I am unable to process your request right now. I've gathered some sources below that might be helpful. Feel free to take a look, or try asking your question in a different way."
        ),
    }


def _get_further_help(language: str, page: Optional[str]) -> str:
    """The configured further-help text, or the page-specific override."""
    entry = (settings.parsed_messages or {}).get(MsgName.further_help.value)
    if not entry:
        return ""
    lang_key = "german" if language == Languages.GERMAN else "english"
    override = best_page_match(
        page, entry.get("page_overrides", []), lambda o: o["match"]
    )
    return (override or entry)[lang_key]


def _get_error_messages(language: str, page: Optional[str] = None) -> dict:
    """All user-facing error messages, translated, with the (page-specific) further-help text."""
    further_help = _get_further_help(language, page)
    suffix = f"\n\n{further_help}" if further_help else ""
    return {k: v + suffix for k, v in _get_base_messages(language).items()}
