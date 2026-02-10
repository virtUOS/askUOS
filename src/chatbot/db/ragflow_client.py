import asyncio
import os
import threading
from typing import Any, List, NamedTuple, Optional

import frontmatter
import httpx
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
        # post = frontmatter.loads(self.content)
        # url = post.get("url", "")
        # return url

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

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance.dbs = {}
                    cls._instance.api_key = os.getenv("RAGFLOW_API_KEY")
                    cls._instance.base_url = (
                        settings.vector_db_settings.settings.base_url
                    )
        return cls._instance

    def _get_client(self) -> httpx.AsyncClient:
        """Create a fresh client every time — httpx is lightweight."""
        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )

    async def get_db_id(self, db_name: str) -> str:
        if db_name in self.dbs:
            return self.dbs[db_name]

        async with self._get_client() as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/datasets",
                params={"name": db_name},
            )
            if resp.status_code == 200:
                datasets = resp.json()
                if datasets and "data" in datasets and datasets["data"]:
                    self.dbs[db_name] = datasets["data"][0]["id"]
                    return self.dbs[db_name]
            raise ValueError(f"Database '{db_name}' not found: {resp.status_code}")

    async def retrieve_chunks(
        self, query: str, db_id: str, page_size: int = NUMBER_CHUNKS_RETRIEVE
    ):
        async with self._get_client() as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/retrieval",
                json={
                    "question": query,
                    "dataset_ids": [db_id],
                    "document_ids": [],
                    "page_size": page_size,
                    "cross_languages": ["German", "English"],
                },
            )
            if resp.status_code == 200:
                r = resp.json()
                return [
                    RetrievedContentRagflow(
                        chunk=Chunk(**chunk), doc_aggs=RetrievedDocs(**docs)
                    )
                    for chunk, docs in zip(r["data"]["chunks"], r["data"]["doc_aggs"])
                ]
            raise ValueError(f"Failed: {resp.status_code} - {resp.text}")

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
