from langchain_core.embeddings import Embeddings

from src.chatbot.embeddings.fast_embed import embed_query
from src.chatbot.embeddings.ollama_embed import get_ollama_embeddings_vector
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings
from src.config.models import EmbeddingType


def get_embeddings(
    query: str, type_embedding: EmbeddingType = settings.embedding.type
) -> list[float]:
    logger.info(f"Initializing {type_embedding} embedding client...")

    try:
        if type_embedding == "FastEmbed":
            # FastEmbed Long texts will be truncated to at most 512 tokens.
            result = embed_query(query)
        elif type_embedding == "Ollama":
            result = get_ollama_embeddings_vector(query)
        else:
            raise ValueError(f"Unknown embedding type: {type_embedding}")

        logger.info(f"{type_embedding} embedding client initialized successfully")
        return result

    except Exception as e:
        logger.error(
            f"Failed to initialize {type_embedding} embedding client: {str(e)}"
        )
        raise
