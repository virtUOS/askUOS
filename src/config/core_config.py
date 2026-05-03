from typing import ClassVar, Literal, Optional, Tuple, Type, Any

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from src.chatbot_log.chatbot_logger import logger

from .models import (
    ApplicationConfig,
    CrawlSettings,
    EmbeddingSettings,
    GraphConfig,
    LogSettings,
    MilvusSettings,
    Model,
    RAGFlowSettings,
    RedisService,
    SearchConfig,
    VectorDBConfig,
    Message,
)


class Settings(BaseSettings):
    """
    Settings class for application configuration.

    This class is a singleton that holds various configuration settings for the application.
    It inherits from `BaseSettings` and uses Pydantic for data validation and settings management.

    """

    _instance: ClassVar[Optional["Settings"]] = None

    # search_config: SearchConfig
    redis: RedisService
    models: list[Model]
    application: ApplicationConfig
    embedding: Optional[EmbeddingSettings] = None
    vector_db_settings: VectorDBConfig
    language: Literal["Deutsch", "English"]
    graph: GraphConfig
    crawl_settings: CrawlSettings
    messages: Optional[list[Message]] = None

    model_config = SettingsConfigDict(yaml_file="./src/backend_config.yaml")
    # TODO move this a global object/context
    time_request_sent: Optional[float] = None
    # TODO remove (these are used for testing)
    # final_output_tokens: list = []
    # final_search_tokens: list = []
    # TODO move to a global object/context
    # if the llm summarization mode is active the summarization result will be not sent to the user
    llm_summarization_mode: bool = False
    log_settings: Optional[LogSettings] = None
    parsed_messages: Optional[dict] = None

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

    def model_post_init(self, context: Any) -> None:
        if self.messages:
            self.parsed_messages = {
                item.msg_name.further_help.value: {
                    "english": item.english,
                    "german": item.german,
                }
                for item in self.messages
            }


settings = Settings()
