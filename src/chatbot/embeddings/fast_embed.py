# Configurations
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from src.config.core_config import settings


# Initialize embeddings with configuration
def get_fast_embed_model():
    return FastEmbedEmbeddings(
        model_name=settings.embedding.connection_settings.model_name,
    )


def embed_query(query: str) -> list[float]:
    """Embed a query using FastEmbed."""
    model = get_fast_embed_model()
    return model.embed_query(query)
