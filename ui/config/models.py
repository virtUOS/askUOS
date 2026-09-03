from typing import Optional

from pydantic import BaseModel, Field


class Legal(BaseModel):
    """
    Configuration for legal information.
    """

    data_protection: str
    imprint: str


class ApiConf(BaseModel):
    api_url: str


class UiConfig(BaseModel):
    page_title: str
    human_avatar_path: str = "/app/ui/static/icons/Icon-User.svg"
    assistant_avatar_path: str = "/app/ui/static/icons/Icon-chatbot.svg"
    favicon_path: str = "/app/ui/static/icons/Icon-chatbot.png"


class WaitingTip(BaseModel):
    """One rotating "while you wait" tip (see WaitingTipsConfig). Title +
    body per language, same per-language-suffix convention as
    ChatPageConfig.greeting_message_english/german."""

    title_english: str
    title_german: str
    body_english: str
    body_german: str
    # Optional CTA URL (e.g. "if you want to apply, take a look here"),
    # shown regardless of language. Rendered as a "Read more" link -- see
    # ui/pages/ask_uos_chat.py::_render_waiting_tip.
    link: Optional[str] = None


class RssFeedConfig(BaseModel):
    """One RSS/Atom feed to pull waiting tips from (see
    ui/utils/utils.py::fetch_rss_waiting_tips), as an alternative or
    supplement to hand-typed WaitingTip entries -- lets a university's
    existing events/news feed drive live content without editing config
    every time something changes. Items show regardless of the session's
    selected language (no translation is attempted; see
    fetch_rss_waiting_tips for why)."""

    url: str
    # Most recent N entries taken from this feed (by published/updated
    # date where the feed provides one, otherwise feed order).
    max_items: int = 5


class WaitingTipsConfig(BaseModel):
    """Config for the rotating tip card shown during answer generation
    (see ui/pages/ask_uos_chat.py::generate_response). Defaults to
    disabled + no tips/feeds, so upgrading an existing deployment's
    ui_config.yml changes nothing unless a university explicitly opts in
    and supplies its own content -- this is exactly the kind of
    university-specific content CLAUDE.md warns against ever hardcoding.
    Static tips and RSS feed items are combined into one rotation pool --
    see ui/pages/ask_uos_chat.py::_get_active_waiting_tips.
    """

    enabled: bool = False
    tips: list[WaitingTip] = Field(default_factory=list)
    rss_feeds: list[RssFeedConfig] = Field(default_factory=list)
    # Sent as the User-Agent header on every RSS fetch (see
    # ui/utils/utils.py::fetch_rss_waiting_tips). 
    rss_user_agent: str = "UniBot/1.0 (RSS feed reader)"
    # How long a fetched feed's items are cached before being re-fetched
    # (see ui/utils/utils.py::_fetch_single_rss_feed) 
    rss_cache_seconds: int = 3600
    # A tip only ever appears once the backend signals it's actually
    # consulting a tool (see generate_response's status-gating) -- there's
    # no separate "wait N seconds before showing anything" delay, since a
    # status event never fires instantly at turn start anyway.
    #
    # How long each individual tip stays on screen is
    # max(rotate_seconds, min_display_seconds) -- min_display_seconds is a
    # readability floor that always wins if it's the larger of the two, so
    # a tip can never be rotated away (or cleared for the real answer)
    # before it's had at least that long visible, regardless of how
    # rotate_seconds is set.
    rotate_seconds: float = 6.0
    min_display_seconds: float = 9.0
    # Cap on how many distinct tips rotate through in one generation round
    # -- past this, the rotation freezes on the last tip shown instead of
    # continuing to cycle for however long the turn takes.
    max_tips_per_turn: int = 2


class ChatPageConfig(BaseModel):
    """
    Configuration for the chat page.
    """

    greeting_message_german: str
    greeting_message_english: str
    # Previously hardcoded directly in ui/pages/ask_uos_chat.py (routed
    # through gettext instead of this config model) — defaults below match
    # that hardcoded text exactly, so existing ui_config.yml files without
    # these keys behave identically. ui_example_config.yml already showed
    # these two keys under chat_page, but they weren't real fields on this
    # model, so setting them had no effect until now.
    delete_message_dialog_box_english: str = (
        "Are you sure you want to delete the chat history? This action cannot be undone."
    )
    delete_message_dialog_box_german: str = (
        "Sind Sie sicher, dass Sie den Chatverlauf löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden."
    )
    waiting_tips: WaitingTipsConfig = Field(default_factory=WaitingTipsConfig)


class StartPageConfig(BaseModel):
    """
    Configuration for the start page.
    """

    welcome_message_english: str
    welcome_message_german: str


class IframePageInfo(BaseModel):
    page: Optional[str] = None
    page_title: Optional[str] = None
