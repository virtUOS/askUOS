from typing import Any
from langchain_core.callbacks import StdOutCallbackHandler
from langchain_openai import ChatOpenAI
from src.config.core_config import settings
from langchain_core.globals import set_llm_cache
from langchain_community.cache import SQLiteCache

from src.chatbot_log.chatbot_logger import logger
from langchain_core.caches import InMemoryCache


# TODO the cached AI answer should contained the sources of the information.
# TODO use vectordb to cache the AI answers
class CustomMemoryCache(InMemoryCache):
    def lookup(self, prompt: str, llm_string: str):
        """Look up based on prompt and llm_string.

        Args:
            prompt: a string representation of the prompt.
                In the case of a Chat model, the prompt is a non-trivial
                serialization of the prompt into the language model.
            llm_string: A string representation of the LLM configuration.

        Returns:
            On a cache miss, return None. On a cache hit, return the cached value.
        """
        result_lookup = self._cache.get((prompt, llm_string), None)
        if result_lookup:
            print(f"Cache hit for prompt: {prompt}")
        return result_lookup


# set_llm_cache(CustomMemoryCache())

# set_llm_cache(SQLiteCache(database_path=".langchain.db"))

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
