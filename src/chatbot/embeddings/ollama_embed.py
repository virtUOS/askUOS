import threading

from langchain_ollama import OllamaEmbeddings

from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings


class OllamaSingleton:
    """
    Singleton class to manage Ollama embeddings.
    Ensures that only one instance of OllamaEmbeddings is created.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    logger.info("Initializing Ollama embeddings client...")
                    cls._instance = OllamaEmbeddings(
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
                    logger.info("Ollama embeddings client initialized successfully")
        return cls._instance


ollama_embedding = OllamaSingleton()

# def get_ollama_embeddings() -> OllamaEmbeddings:
#     """
#     Get Ollama embeddings configured with the settings from the application.
#     Returns:
#         OllamaEmbeddings: Configured Ollama embeddings instance.
#     """

#     embeddings = OllamaEmbeddings(
#         model=settings.embedding.connection_settings.model_name,
#         base_url=settings.embedding.connection_settings.base_url,
#         client_kwargs={
#             "headers": {
#                 "Authorization": settings.embedding.connection_settings.headers[
#                     "Authorization"
#                 ]
#             }
#         },
#     )

#     return embeddings


def get_ollama_embeddings_vector(query: str) -> list[float]:
    """
    Get the vector representation of a query using Ollama embeddings.

    Args:
        query (str): The input query to be embedded.

    Returns:
        list[float]: The vector representation of the query.
    """

    # TODO: Needs to  implemented asynchronously
    return ollama_embedding.embed_query(query)
