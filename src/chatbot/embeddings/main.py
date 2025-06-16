from langchain_core.embeddings import Embeddings

from src.chatbot.embeddings.fast_embed import get_fast_embed_model
from src.chatbot.embeddings.ollama_embed import get_ollama_embeddings
from src.chatbot_log.chatbot_logger import logger
from src.config.models import EmbeddingType


def get_embeddings(type_embedding: EmbeddingType = "FastEmbed") -> Embeddings:
    logger.info(f"Initializing {type_embedding} embedding client...")

    try:
        if type_embedding == "FastEmbed":
            # FastEmbed Long texts will be truncated to at most 512 tokens.
            result = get_fast_embed_model()
        elif type_embedding == "Ollama":
            result = get_ollama_embeddings()
        else:
            raise ValueError(f"Unknown embedding type: {type_embedding}")

        logger.info(f"{type_embedding} embedding client initialized successfully")
        return result

    except Exception as e:
        logger.error(
            f"Failed to initialize {type_embedding} embedding client: {str(e)}"
        )
        raise
