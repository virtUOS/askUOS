"""Match the host page a client sent (``page``) against configured overrides.

Shared by the backend and the Streamlit UI so both resolve per-page texts the
same way. Pure functions, no third-party imports.
"""

import re
from typing import Callable, Iterable, Optional, TypeVar

T = TypeVar("T")


def normalize_page(url: str) -> str:
    """Lowercase and drop scheme, leading "www." and trailing slashes."""
    url = re.sub(r"^https?://", "", url.strip().lower())
    return re.sub(r"^www\.", "", url).rstrip("/")


def best_page_match(
    page: Optional[str], items: Iterable[T], get_match: Callable[[T], str]
) -> Optional[T]:
    """
    Return the item whose match string is the best fit for ``page``, or None.

    ``page`` and each match are normalized (case, scheme, "www.", trailing
    slash). A match applies if it equals the page or is a parent of it on a
    "/" boundary, so "sport.example.de" and "/sport" cover everything below
    them but "/sport" does not cover "/sportwissenschaft". The longest
    applicable match wins.
    """
    page = normalize_page(page or "")
    if not page:
        return None

    best: Optional[T] = None
    best_len = -1
    for item in items:
        match = normalize_page(get_match(item))
        if not match or (page != match and not page.startswith(match + "/")):
            continue
        if len(match) > best_len:
            best, best_len = item, len(match)
    return best
