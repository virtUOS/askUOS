from pydantic import BaseModel
from typing import Optional


class Legal(BaseModel):
    """
    Configuration for legal information.
    """

    data_protection: str
    imprint: str


class UiConfig(BaseModel):
    page_title: str


class ChatPageConfig(BaseModel):
    """
    Configuration for the chat page.
    """

    greeting_message_german: str
    greeting_message_english: str


class StartPageConfig(BaseModel):
    """
    Configuration for the start page.
    """

    welcome_message_english: str
    welcome_message_german: str


class IframePageInfo(BaseModel):
    page: Optional[str] = None
    page_title: Optional[str] = None
