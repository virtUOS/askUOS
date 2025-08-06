import asyncio
import os
import threading
from typing import Any, List, Optional

import aiohttp
import nest_asyncio
import requests
from dotenv import load_dotenv
from pydantic import BaseModel

from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings


class Chunk(BaseModel):
    content: str
    content_ltks: str
    dataset_id: str
    doc_type_kwd: str
    document_id: str
    document_keyword: str
    highlight: str
    id: str
    image_id: str
    important_keywords: List[str]
    positions: List[List[Any]]
    similarity: float
    term_similarity: float
    vector_similarity: float


class RAGFlowSingleton:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(RAGFlowSingleton, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("RAGFLOW_API_KEY")
        self.base_url = base_url or settings.ragflow_settings.base_url
        self.dbs = {}
        self._session = None
        self._session_lock = threading.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proper configuration."""
        if self._session is None or self._session.closed:
            with self._session_lock:
                if self._session is None or self._session.closed:
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    connector = aiohttp.TCPConnector(
                        limit=100,  # Total connection pool size
                        limit_per_host=30,  # Per host connection limit
                        ttl_dns_cache=300,  # DNS cache TTL
                        use_dns_cache=True,
                    )
                    self._session = aiohttp.ClientSession(
                        timeout=timeout,
                        connector=connector,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    )
        return self._session

    async def close_session(self):
        """Properly close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_db_id(self, db_name: str) -> str:
        """Get the database ID for a given database name."""
        if db_name in self.dbs.keys():
            return self.dbs[db_name]

        session = await self._get_session()

        try:
            async with session.get(
                f"{self.base_url}/api/v1/datasets", params={"name": db_name}
            ) as response:
                if response.status == 200:
                    datasets = await response.json()
                    if datasets and "data" in datasets and datasets["data"]:
                        self.dbs[db_name] = datasets["data"][0]["id"]
                        logger.debug(
                            f"Database ID for '{db_name}': {self.dbs[db_name]}"
                        )
                        return datasets["data"][0]["id"]
                    else:
                        logger.error(f"Database '{db_name}' not found.")
                        raise ValueError(f"Database '{db_name}' not found.")
                else:
                    logger.error(f"Failed to fetch database ID: {response.status}")
                    error_text = await response.text()
                    raise ValueError(
                        f"Failed to fetch database ID: {response.status} - {error_text}"
                    )
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching database ID: {e}")
            raise ValueError(f"Network error: {e}")

    async def retrieve_chunks(
        self,
        query: str,
        db_id: str,
        page_size: int = 10,
    ) -> List[Chunk]:
        """Retrieve chunks from the RAGFlow database based on a query."""
        session = await self._get_session()

        try:
            async with session.post(
                f"{self.base_url}/api/v1/retrieval",
                headers={"Content-Type": "application/json"},
                json={
                    "question": query,
                    "dataset_ids": [db_id],
                    "document_ids": [],
                    "page_size": page_size,
                    "cross_languages": ["German", "English"],
                },
            ) as response:
                if response.status == 200:
                    r = await response.json()
                    chunks = [Chunk(**chunk) for chunk in r["data"]["chunks"]]
                    return chunks
                else:
                    logger.error(f"Failed to retrieve chunks: {response.status}")
                    error_text = await response.text()
                    raise ValueError(
                        f"Failed to retrieve chunks: {response.status} - {error_text}"
                    )
        except aiohttp.ClientError as e:
            logger.error(f"Network error while retrieving chunks: {e}")
            raise ValueError(f"Network error: {e}")

    async def get_docs(self, query: str, db_name: str) -> List[Chunk]:
        """Async version for use within existing event loops."""
        chunks = []
        try:
            db_id = await self.get_db_id(db_name)
            chunks = await self.retrieve_chunks(query, db_id)
            logger.debug(
                f"Retrieved {len(chunks)} chunks for query '{query}' in database '{db_name}'."
            )
        except Exception as e:
            logger.error(f"Error retrieving chunks: {e}")
        return chunks

    def run_sync(self, query: str, db_name: str) -> List[Chunk]:
        """Synchronous version that handles event loop creation safely."""
        try:
            # Try to get existing event loop
            loop = asyncio.get_running_loop()
            nest_asyncio.apply()  # Allow nested event loops

            return asyncio.run_coroutine_threadsafe(
                self.get_docs(query, db_name), loop
            ).result()
        except RuntimeError:
            # No event loop exists, safe to create one
            return asyncio.run(self.get_docs(query, db_name))

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.run_sync(*args, **kwds)

    def __del__(self):
        """Cleanup when instance is destroyed."""
        if hasattr(self, "_session") and self._session and not self._session.closed:
            # Note: This won't work properly as __del__ is sync
            # Better to explicitly call close_session()
            pass


ragflowretriever = RAGFlowSingleton()


ragflowretriever("Credit points computer science", "UOS_PO")
print()
