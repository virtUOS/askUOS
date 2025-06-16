import os

import dotenv

dotenv.load_dotenv()
import asyncio
import logging
import os
from typing import List, Optional

import nest_asyncio
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_milvus import Milvus

from src.chatbot.embeddings.main import get_embeddings
from src.config.core_config import settings

# # Configurations
# EMBEDDING_MODEL = "intfloat/multilingual-e5-large"


# # Initialize embeddings
# embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)

# TODO: Move to config.yml

URI = os.getenv("MILVUS_URL")
MILVUS_USER = os.getenv("MILVUS_USER")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD")


# TODO this function is implemented to solve bug with Milvus and async operations: RuntimeError: There is no current event loop in thread 'ScriptRunner.scriptThread'.
# TODO check if bug is fixed in the latest version of Milvus or Langchain
def ensure_event_loop():
    """Ensure there's an event loop available for (e.g. Milvus) async operations."""
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
        # If we get here, there's a running loop - apply nest_asyncio to allow nesting
        nest_asyncio.apply()
        return loop
    except RuntimeError:
        # No running event loop, create a new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                # Event loop is closed, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # No event loop at all, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop


def get_milvus_client(collection_name: str) -> Milvus:
    ensure_event_loop()
    embeddings = get_embeddings(settings.embedding.type)
    vector_store = Milvus(
        embedding_function=embeddings,
        connection_args={"uri": URI, "token": f"{MILVUS_USER}:{MILVUS_PASSWORD}"},
        collection_name=collection_name,
    )

    return vector_store


def get_retriever(collection_name: str) -> VectorStoreRetriever:

    vector_store = get_milvus_client(collection_name)
    retriever = vector_store.as_retriever(
        search_type="similarity", search_kwargs={"k": 5}
    )

    return retriever


print()

# web_index_retriever = get_milvus_client_retriever("web_index")

# print()
# # Example usage:
# results = retriever.invoke(
#     "I finished my application but I did not receive a confirmation email"
# )


# vector_store = Milvus(
#     embedding_function=embeddings,
#     connection_args={"uri": URI, "token": f"{MILVUS_USER}:{MILVUS_PASSWORD}"},
#     collection_name="examination_regulations",
# )


# for doc in results:
#     print(f"* {doc.page_content} [{doc.metadata}]")

# # LIKE --> infix match
# vector_store.similarity_search_with_score(
#     "master arbeit", k=1, expr='source LIKE "%Biologie%"'
# )
