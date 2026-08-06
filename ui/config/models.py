from typing import Optional

from pydantic import BaseModel


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


class StartPageConfig(BaseModel):
    """
    Configuration for the start page.
    """

    welcome_message_english: str
    welcome_message_german: str


class IframePageInfo(BaseModel):
    page: Optional[str] = None
    page_title: Optional[str] = None
