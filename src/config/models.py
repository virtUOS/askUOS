from enum import Enum
from typing import ClassVar, List, Literal, Optional, Tuple, Type, Union

from pydantic import BaseModel

EmbeddingType = Literal["FastEmbed", "Ollama"]


class VectorDBTypes(str, Enum):
    MILVUS = "Milvus"
    INFINITY_RAGFLOW = "Infinity-RAGFlow"


class CollectionNames(str, Enum):
    """
    Collection names used in the application.
    """

    EXAMINATION_REGULATIONS = "examination_regulations"
    FAQ = "faq"
    TROUBLESHOOTING = "troubleshooting"


class ProviderNames(str, Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    SELF_HOSTED = "self-hosted"


class RoleNames(str, Enum):
    MAIN = "main"
    HELPER = "helper"


class SearchConfig(BaseModel):
    """
    Configuration for the search service.
    """

    search_url: str
    service: str


class Model(BaseModel):
    """
    Configuration for the model being used.
    """

    provider: ProviderNames
    role: RoleNames
    model_name: str


class ApplicationConfig(BaseModel):
    """
    Configuration for the application.
    """

    debug: bool
    recursion_limit: int = 12
    tracing: bool = False
    opik_project_name: str = "askUOSTesting"


class EmbeddingConnectionSettings(BaseModel):
    """Settings for Ollama embeddings"""

    model_name: str = (
        "intfloat/multilingual-e5-large"  # e.g., "llama2", "mistral", "intfloat/multilingual-e5-large"
    )
    base_url: Optional[str] = "http://localhost:11434"
    headers: Optional[dict] = None


class EmbeddingSettings(BaseModel):
    """Settings for text embedding"""

    type: EmbeddingType = "FastEmbed"
    connection_settings: EmbeddingConnectionSettings
    chunk_size: int = (
        1800  # Size of each chunk in characters (Only crawler uses a text splitter)
    )
    chunk_overlap: int = 50
    batch_size: int = 256


class LogSettings(BaseModel):
    delete_logs_days: int = 90  # Number of days to keep logs before deletion


class MilvusSettings(BaseModel):
    """Settings for Milvus vector database"""

    uri: Optional[str] = "http://localhost:19530"
    host: Optional[str] = None
    port: int = 19530
    token: Optional[str] = "root:Milvus"


class RAGFlowSettings(BaseModel):
    """
    Configuration for RAGFlow settings.
    """

    base_url: str
    chunk_size: int = 10  # Number of chunks to retrieve per request


class VectorDBConfig(BaseModel):
    """
    Configuration for the vector database.
    """

    type: VectorDBTypes = VectorDBTypes.MILVUS
    settings: Union[MilvusSettings, RAGFlowSettings]


class CrawlSettings(BaseModel):
    """Settings for web crawler behavior"""

    base_url: str
    crawl_payload: dict  # TODO : requires special validation, use the crawl4ai schema
    ttl_redis: int


class GraphConfig(BaseModel):
    # summarize if context is >= summary_threshold
    summary_threshold: int
