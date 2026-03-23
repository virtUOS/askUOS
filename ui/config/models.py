from pydantic import BaseModel


class Legal(BaseModel):
    """
    Configuration for legal information.
    """

    data_protection: str
    imprint: str


class ChatPageConfig(BaseModel):
    """
    Configuration for the chat page.
    """

    delete_message_dialog_box_english: str
    delete_message_dialog_box_german: str


class StartPageConfig(BaseModel):
    """
    Configuration for the start page.
    """

    welcome_message_english: str
    welcome_message_german: str
