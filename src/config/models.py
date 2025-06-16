from typing import ClassVar, List, Literal, Optional, Tuple, Type

from pydantic import BaseModel

EmbeddingType = Literal["FastEmbed", "Ollama"]


class SearchConfig(BaseModel):
    """
    Configuration for the search service.
    """

    search_url: str
    service: str


class ModelConfig(BaseModel):
    """
    Configuration for the model being used.
    """

    model_name: str
    context_window: int  # Number of allowed tokens


class Legal(BaseModel):
    """
    Configuration for legal information.
    """

    data_protection: str
    imprint: str


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
