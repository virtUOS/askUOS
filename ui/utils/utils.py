import html
import re
from urllib.parse import urlparse

import feedparser
import requests
import streamlit as st
from streamlit import session_state

from src.chatbot_log.chatbot_logger import logger
from ui.config.app_config import app_settings
from ui.config.models import IframePageInfo, RssFeedConfig
from ui.utils.language import get_translator


def initialize_session_sate() -> None:
    """
    Initializes the session state with default values if they are not already set.
    """
    # Initialization
    defaults = {
        # Driven by ui_config.yml's configured `language` default, so a
        # university setting language: "English" actually sees English text
        # on first load instead of always getting German until the language
        # radio button is manually toggled.
        "_": get_translator(app_settings.language),
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
        # Set True right before generate_response starts streaming,
        # cleared in its own `finally` block -- which also fires the
        # backend cancel immediately, synchronously, if that block finds
        # the run was interrupted mid-generation (native chat_input stop
        # button, or any other widget click) rather than completed
        # normally. run() also checks this flag at the top of every script
        # run as a defensive fallback. See ChatApp.run()/generate_response
        # in ask_uos_chat.py.
        "is_generating": False,
    }

    for key, value in defaults.items():
        if key not in session_state:
            session_state[key] = value


def setup_page() -> None:
    """Set up the Streamlit page configuration."""
    st.set_page_config(
        page_title=app_settings.ui.page_title,
        page_icon=app_settings.ui.favicon_path,
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


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
# Keeps a feed-derived tip body roughly the same size as a hand-typed one --
# the card is designed for a short blurb, not a full article excerpt.
RSS_TIP_BODY_MAX_CHARS = 220


def _clean_rss_text(raw: str) -> str:
    """Strip HTML tags/entities out of a raw RSS/Atom title or summary field
    and collapse whitespace, so it renders as plain text the same way a
    hand-typed WaitingTip body does. Real-world feeds routinely embed HTML
    (<p>, <a>, entities) in their description/summary -- left as-is, the tip
    card's html.escape() step (see ask_uos_chat.py::_render_waiting_tip)
    would show literal "&lt;p&gt;" tags to the user instead of clean text.
    """
    if not raw:
        return ""
    text = _HTML_TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > RSS_TIP_BODY_MAX_CHARS:
        text = text[: RSS_TIP_BODY_MAX_CHARS - 1].rstrip() + "…"
    return text


def _safe_rss_link(raw) -> str | None:
    """Only keep an RSS entry's link if it's an ordinary http(s) URL. Feed
    content is a lower-trust input than admin-typed config -- a malicious
    or compromised feed could otherwise smuggle a `javascript:` (or other
    exotic-scheme) URL into a rendered href. Drops just the link, not the
    whole tip, when it doesn't pass."""
    if not raw:
        return None
    try:
        scheme = urlparse(raw).scheme.lower()
    except ValueError:
        return None
    return raw if scheme in ("http", "https") else None


# Not configurable -- purely a technical content-type negotiation, unlike
# the User-Agent (see WaitingTipsConfig.rss_user_agent), which is about how
# a deployment identifies itself and is an admin's call, not a fixed
# implementation detail.
_RSS_ACCEPT_HEADER = "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"


# Evaluated once at import time, same as every other config value in this
# app (there's no mechanism, or need, to change it without a restart).
@st.cache_data(ttl=app_settings.chat_page.waiting_tips.rss_cache_seconds)
def _fetch_single_rss_feed(url: str, max_items: int, user_agent: str) -> list[dict]:
    """Fetch and parse one RSS/Atom feed into
    [{"title": ..., "body": ..., "link": ...}, ...], newest first where the
    feed provides dates (Python's sort is stable, so entries without a date
    keep their original feed-order among themselves), capped at
    `max_items`. Never raises -- any network/parse failure is logged and
    treated as "this feed has no items right now" (see
    fetch_rss_waiting_tips), the same graceful-degradation approach this
    codebase's backend already uses for MCP subagent failures.

    `user_agent` (WaitingTipsConfig.rss_user_agent) is sent as-is. Plain
    requests.get() with no headers at all uses python-requests' own
    default User-Agent ("python-requests/X.Y") and no Accept header --
    several real CMS platforms (TYPO3 in particular, common at German
    universities) and WAFs/CDNs reject that with a 403 or, less
    intuitively, a bare 404, even though the identical URL opens fine in a
    real browser. Moving off that default signature is what actually
    avoids the block; self-identifying with a descriptive UA beyond that
    is a courtesy for the site operator (the Googlebot/Feedly-fetcher
    convention), not itself a technical requirement -- left entirely up to
    each deployment's admin rather than fixed in code.
    """
    try:
        headers = {"User-Agent": user_agent, "Accept": _RSS_ACCEPT_HEADER}
        response = requests.get(url, timeout=4, headers=headers)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as e:
        logger.warning(f"[WAITING-TIPS] Could not fetch/parse RSS feed {url}: {e}")
        return []

    entries = list(parsed.entries or [])
    entries.sort(
        key=lambda entry: entry.get("published_parsed")
        or entry.get("updated_parsed")
        or (),
        reverse=True,
    )

    tips = []
    for entry in entries[:max_items]:
        title = _clean_rss_text(entry.get("title", ""))
        if not title:
            continue
        tips.append(
            {
                "title": title,
                "body": _clean_rss_text(entry.get("summary", "")),
                "link": _safe_rss_link(entry.get("link")),
            }
        )
    return tips


def fetch_rss_waiting_tips(feeds: list[RssFeedConfig], user_agent: str) -> list[dict]:
    """Fetch waiting tips from every configured RSS feed, combined into one
    list (see WaitingTipsConfig.rss_feeds). Items show regardless of the
    session's selected language -- no per-feed language filtering, no
    translation attempted (see RssFeedConfig's docstring for why). Feeds
    are fetched sequentially, not in parallel: a cache-cold fetch only
    happens once per feed per rss_cache_seconds window process-wide (see
    _fetch_single_rss_feed), so the added worst-case latency from a slow
    feed is bounded and rare, not worth the complexity of parallelizing for
    a first version. Each feed is independently guarded against failure by
    _fetch_single_rss_feed -- one broken/slow feed never drops the others.

    `user_agent` is WaitingTipsConfig.rss_user_agent, sent identically to
    every configured feed -- one deployment identifies itself the same way
    to all the feeds it reads, rather than per-feed.
    """
    tips = []
    for feed in feeds:
        tips.extend(_fetch_single_rss_feed(feed.url, feed.max_items, user_agent))
    return tips
