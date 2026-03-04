import gettext
from functools import lru_cache


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


def _get_error_messages(language: str) -> dict:
    """All user-facing error messages, translated."""
    _ = get_translator(language)

    further_help = _(
        """If you need personal assistance regarding studying at the university, you can visit the [StudiOS]({}) (Studierenden-Information Osnabrück) or [ZSB]({}) (Zentrale Studienberatung Osnabrück) website."""
    )
    further_help = further_help.format(
        "https://www.uni-osnabrueck.de/universitaet/organisation/studierenden-information-osnabrueck-studios/",
        "https://www.zsb-os.de/",
    )

    return {
        "recursion": _(
            "I'm sorry, but I couldn't find enough information to fully answer your question. Could you please try rephrasing your query and ask again?"
        )
        + f"\n\n{further_help}",
        "search_error": _(
            "I'm sorry, something went wrong while connecting to the data provided. If the error persists, please reach out to the administrators for assistance."
        )
        + f"\n\n{further_help}",
        "generic": _(
            "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
        )
        + f"\n\n{further_help}",
    }
