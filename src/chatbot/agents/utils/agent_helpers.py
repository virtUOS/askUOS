import os
import sys
import threading
from typing import Any

sys.path.append("/app")
from langchain_community.cache import SQLiteCache
from langchain_core.caches import InMemoryCache
from langchain_core.callbacks import StdOutCallbackHandler
from langchain_core.globals import set_llm_cache
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings
from src.config.models import Model, ProviderNames, RoleNames


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


class LLMMixin:
    def _build_llm_obj(self, model_conf: Model):
        if model_conf.provider == ProviderNames.GOOGLE:
            self.llm = ChatGoogleGenerativeAI(
                model=model_conf.model_name,
                temperature=1.0,
                max_retries=2,
                streaming=True,
                callbacks=[StdOutCallbackHandler()],
            )
        elif (
            model_conf.provider == ProviderNames.OPENAI
            or model_conf.provider
            == ProviderNames.SELF_HOSTED  # self-hosted model must be openai compatible
        ):
            self.llm = ChatOpenAI(
                model=model_conf.model_name,
                temperature=0,
                streaming=True,
                callbacks=[StdOutCallbackHandler()],
            )

        else:
            ValueError("Model provided not supported")


class ChatLlm(LLMMixin):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ChatLlm, cls).__new__(cls)

        return cls._instance

    def __init__(self, model_conf: Model):
        if not self.__dict__:
            self._build_llm_obj(model_conf)


class ChatLlmOptional(LLMMixin):
    """
    Model used for law-level complexity tasks (Usualla a small fast LLM)
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ChatLlmOptional, cls).__new__(cls)
        return cls._instance

    def __init__(self, model_conf: Model):
        if not self.__dict__:
            self._build_llm_obj(model_conf)


class ReasoningLlm:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ReasoningLlm, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self.__dict__:

            self.llm_chat_open_ai = ChatOpenAI(
                model="gpt-5-nano",
                temperature=1,
                streaming=True,
                callbacks=[StdOutCallbackHandler()],
            )

    def __call__(self, *args, **kwargs) -> Any:
        return self.llm_chat_open_ai


class _ModelRegistry:
    """Container for lazily-initialized model singletons."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(_ModelRegistry, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.create_models()
        self._initialized = True

    def create_models(self):
        models = settings.models
        self.chat_llm = None
        self.llm_optional = None
        for m in models:
            if m.role == RoleNames.MAIN:
                self.chat_llm = ChatLlm(m)
            elif m.role == RoleNames.HELPER:
                self.llm_optional = ChatLlmOptional(m)
            else:
                raise ValueError("Model Role not supported")
        if not self.chat_llm:
            raise ValueError("An LLM must be provided")
        if not self.llm_optional:
            self.llm_optional = self.chat_llm


model_registry = _ModelRegistry()
