from langchain_ollama import OllamaEmbeddings
from src.config.core_config import settings


def get_ollama_embeddings() -> OllamaEmbeddings:
    """
    Get Ollama embeddings configured with the settings from the application.
    Returns:
        OllamaEmbeddings: Configured Ollama embeddings instance.
    """

    embeddings = OllamaEmbeddings(
        model=settings.embedding.connection_settings.model_name,
        base_url=settings.embedding.connection_settings.base_url,
        client_kwargs={
            "headers": {
                "Authorization": settings.embedding.connection_settings.headers[
                    "Authorization"
                ]
            }
        },
    )

    return embeddings


def get_ollama_embeddings_vector(query: str) -> list[float]:
    """
    Get the vector representation of a query using Ollama embeddings.

    Args:
        query (str): The input query to be embedded.

    Returns:
        list[float]: The vector representation of the query.
    """
    embeddings = get_ollama_embeddings()
    return embeddings.embed_query(query)
