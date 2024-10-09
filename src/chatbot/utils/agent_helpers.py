from typing import Any
from langchain_core.callbacks import StdOutCallbackHandler
from langchain_openai import ChatOpenAI
from src.config.core_config import settings

OPEN_AI_MODEL = settings.model.model_name


class ChatLlm:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ChatLlm, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self.__dict__:
            self.llm_chat_open_ai = ChatOpenAI(
                model=OPEN_AI_MODEL,
                temperature=0,
                streaming=True,
                callbacks=[StdOutCallbackHandler()],
            )

    def __call__(self, *args, **kwargs) -> Any:
        return self.llm_chat_open_ai


llm = ChatLlm()
