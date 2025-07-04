import asyncio
import threading
from typing import List, Optional

import nest_asyncio
from pymilvus import MilvusClient

from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

# from langchain_core.vectorstores import VectorStoreRetriever
# from langchain_milvus import Milvus
# from pymilvus import Collection
# from pymilvus import MilvusClient
# from src.chatbot.embeddings.main import get_embeddings
# from src.chatbot_log.chatbot_logger import logger
# from src.config.core_config import settings


HIS_IN_ONE_COLLECTON = "troubleshooting"
EXAMINATION_REGULATIONS_COLLECTION = "examination_regulations"


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


# def get_milvus_client(collection_name: str) -> Optional[Milvus]:
#     ensure_event_loop()

#     try:
#         embeddings = get_embeddings(settings.embedding.type)
#         vector_store = Milvus(
#             embedding_function=embeddings,
#             connection_args={
#                 "uri": settings.milvus_settings.uri,
#                 "token": settings.milvus_settings.token,
#             },
#             collection_name=collection_name,
#         )

#         logger.info("[VECTOR DB]Milvus client initialized successfully")
#         return vector_store
#     except Exception as e:
#         logger.error(f"[VECTOR DB]Failed to initialize Milvus client: {e}")
#         return None


class MilvusSingleton:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(MilvusSingleton, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the singleton with Milvus connections and collections."""
        self.client = None
        self.collections = {}
        self._load_collections()

    def _load_collections(self):
        """Load frequently used collections."""
        try:

            self.client = MilvusClient(
                uri=settings.milvus_settings.uri,
                token=settings.milvus_settings.token,
            )
            # Use pymilvus Collection to load collections
            self.collections["examination_regulations"] = self.client.load_collection(
                collection_name="examination_regulations",
            )
            self.collections["troubleshooting"] = self.client.load_collection(
                collection_name="troubleshooting",
            )
            logger.info("[VECTOR DB]Collections loaded successfully")
        except Exception as e:
            logger.error(f"[VECTOR DB]Failed to load collections: {e}")

    def get_collection(self, collection_name):
        """Get a loaded collection by name."""
        return self.collections.get(collection_name)

    def release_collections(self):
        """Close all connections."""
        for coll_name, collection in self.collections.items():
            self.client.release_collection(collection_name=coll_name)
        logger.info("[VECTOR DB]Connections closed")

    def close_connections(self):
        """Close the Milvus client connection."""
        if self.client:
            self.client.close()
            logger.info("[VECTOR DB]Milvus client connection closed")
        else:
            logger.warning("[VECTOR DB]No Milvus client to close")


milvus_client = MilvusSingleton()
