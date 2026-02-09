import asyncio
import os
import threading
from typing import Any, List, NamedTuple, Optional

import aiohttp
import requests
from dotenv import load_dotenv
from pydantic import BaseModel

from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

# TODO delete once metadata is added to RAGFlow API
FAQ_BASE_URL = "https://uni-osnabrueck.de/"
NUMBER_CHUNKS_RETRIEVE = 10  # number of chunks to retrieve


class RetrievedDocs(BaseModel):
    count: int
    doc_id: str
    doc_name: str


class Chunk(BaseModel):
    content: str
    content_ltks: str
    dataset_id: str
    doc_type_kwd: str
    document_id: str
    document_keyword: str  # documents name
    highlight: str
    id: str
    image_id: str
    important_keywords: List[str]
    positions: List[List[Any]]
    similarity: float
    term_similarity: float
    vector_similarity: float

    # TODO delete once metadata is added to RAGFlow API
    @property
    def url_reference_askuos(self) -> str:
        """Generate URL reference."""
        file_name = os.path.splitext(self.document_keyword.replace("_", "/"))[0]
        return f"{FAQ_BASE_URL}{file_name}"

    @property
    def page(self) -> int:
        """Compute the page number from positions."""
        if self.positions:
            return self.positions[0][0]
        return 0  # Default to 0 if positions are empty


class RetrievedContentRagflow(BaseModel):
    chunk: Chunk
    doc_aggs: RetrievedDocs


class RAGFlowSingleton:
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    _init_lock: Optional[asyncio.Lock] = None

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(RAGFlowSingleton, cls).__new__(cls)
        return cls._instance

    @classmethod
    def _get_init_lock(cls) -> asyncio.Lock:
        """Lazily create the asyncio lock in the current event loop."""
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()
        return cls._init_lock

    async def _ensure_initialized(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ):

        async with self._get_init_lock():
            if not self._initialized:
                self.api_key = api_key or os.getenv("RAGFLOW_API_KEY")
                self.base_url = (
                    base_url or settings.vector_db_settings.settings.base_url
                )
                self.dbs = {}
                self._aio_session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=aiohttp.ClientTimeout(
                        total=None, connect=None, sock_connect=None, sock_read=None
                    ),
                )
                self._initialized = True
                logger.debug("RAGFlowSingleton initialized")

    async def close(self) -> None:
        if (
            hasattr(self, "_aio_session")
            and self._aio_session
            and not self._aio_session.closed
        ):
            await self._aio_session.close()
            self._initialized = False

    async def get_db_id(self, db_name: str) -> str:
        """Get the database ID for a given database name."""
        # make sure this method was run, before executing this function await self._ensure_initialized()
        await self._ensure_initialized()
        if db_name in self.dbs:
            return self.dbs[db_name]
        try:
            logger.debug(f"Getting id for {db_name}")

            resp = await asyncio.wait_for(
                self._aio_session.get(
                    f"{self.base_url}/api/v1/datasets",
                    params={"name": db_name},
                ),
                timeout=30,
            )

            async with resp:
                if resp.status == 200:
                    datasets = await resp.json()
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
                    text = await resp.text()
                    logger.error(
                        f"Failed to fetch database ID. DB name: {db_name}, Response Status: {resp.status}"
                    )
                    raise ValueError(
                        f"Failed to fetch database ID: {resp.status} - {text}"
                    )
        except Exception as e:
            logger.error(f"Network error while fetching database ID: {e}")
            raise ValueError(f"Network error: {e}")

    async def retrieve_chunks(
        self,
        query: str,
        db_id: str,
        page_size: int = NUMBER_CHUNKS_RETRIEVE,
    ) -> List[Chunk]:
        """Retrieve chunks from the RAGFlow database based on a query."""
        try:

            resp = await asyncio.wait_for(
                self._aio_session.post(
                    f"{self.base_url}/api/v1/retrieval",
                    headers={"Content-Type": "application/json"},
                    json={
                        "question": query,
                        "dataset_ids": [db_id],
                        "document_ids": [],
                        "page_size": page_size,
                        "cross_languages": ["German", "English"],
                    },
                ),
                timeout=30,
            )
            async with resp:
                if resp.status == 200:
                    r = await resp.json()
                    retrieved_content = [
                        RetrievedContentRagflow(
                            chunk=Chunk(**chunk), doc_aggs=RetrievedDocs(**docs)
                        )
                        for chunk, docs in zip(
                            r["data"]["chunks"], r["data"]["doc_aggs"]
                        )
                    ]
                    return retrieved_content
                else:
                    text = await resp.text()
                    logger.error(
                        f"[RAGFlow]Failed to retrieve content from RAGFlow: {resp.status}"
                    )
                    raise ValueError(
                        f"[RAGFlow]Failed to retrieve content from RAGFlow: {resp.status} - {text}"
                    )
        except aiohttp.ClientError as e:
            logger.error(f"[RAGFlow]Network error while retrieving chunks: {e}")
            raise

    async def get_chunks(self, query: str, db_name: str) -> List[Chunk]:

        chunks = []
        try:
            db_id = await self.get_db_id(db_name)
            chunks = await self.retrieve_chunks(query, db_id)
            logger.debug(
                f"[RAGFlow]Retrieved {len(chunks)} chunks for query '{query}' in database '{db_name}'."
            )
        except Exception as e:
            logger.error(f"[RAGFlow]Error retrieving chunks: {e}")
        return chunks

    async def run(self, *args: Any, **kwds: Any) -> Any:
        return await self.get_chunks(*args, **kwds)


ragflow_object = RAGFlowSingleton()

if __name__ == "__main__":
    # for testing purposes
    asyncio.run(
        ragflow_object.run("Credit points computer science", "examination_regulations")
    )
    print()
