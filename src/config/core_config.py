from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from typing import Type, Tuple, Literal, ClassVar, Optional
from .models import SearchConfig, ModelConfig, Legal
from src.chatbot_log.chatbot_logger import logger
import time


class Settings(BaseSettings):
    """
    Settings class for application configuration.

    This class is a singleton that holds various configuration settings for the application.
    It inherits from `BaseSettings` and uses Pydantic for data validation and settings management.

    """

    _instance: ClassVar[Optional["Settings"]] = None

    search_config: SearchConfig
    model: ModelConfig
    language: Literal["Deutsch", "English"]
    legal: Optional[Legal] = (
        None  # Optional legal information (e.g., data protection, imprint)
    )
    model_config = SettingsConfigDict(yaml_file="config.yaml")
    # TODO move this a global object/context
    time_request_sent: Optional[float] = None
    # TODO remove (these are used for testing)
    # final_output_tokens: list = []
    # final_search_tokens: list = []
    # TODO move to a global object/context
    # if the llm summarization mode is active the summarization result will be not sent to the user
    llm_summarization_mode: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
        return cls._instance

    def __init__(self, **data):
        if not self.__dict__:
            super().__init__(**data)
            logger.debug(f"Settings initialized: {self.model_dump_json()}")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (YamlConfigSettingsSource(settings_cls),)


settings = Settings()
