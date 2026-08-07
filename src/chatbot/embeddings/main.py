from src.chatbot.agents.utils.agent_helpers import model_registry


def get_embeddings(query: str) -> list[float]:
    return model_registry.embedding_llm.embeddings.embed_query(query)
