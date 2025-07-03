import asyncio
from typing import List, Optional

import nest_asyncio
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_milvus import Milvus

from src.chatbot.embeddings.main import get_embeddings
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings


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


def get_milvus_client(collection_name: str) -> Optional[Milvus]:
    ensure_event_loop()

    try:
        embeddings = get_embeddings(settings.embedding.type)
        vector_store = Milvus(
            embedding_function=embeddings,
            connection_args={
                "uri": settings.milvus_settings.uri,
                "token": settings.milvus_settings.token,
            },
            collection_name=collection_name,
        )

        logger.info("[VECTOR DB]Milvus client initialized successfully")
        return vector_store
    except Exception as e:
        logger.error(f"[VECTOR DB]Failed to initialize Milvus client: {e}")
        return None
