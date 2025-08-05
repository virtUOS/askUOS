import asyncio
import os
import threading
from typing import Any, List, Optional

import aiohttp
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

    def get_db_id(self, db_name: str) -> str:
        """
        Get the database ID for a given database name.

        """
        if db_name in self.dbs.keys():
            return self.dbs[db_name]

        response = requests.get(
            f"{self.base_url}/api/v1/datasets?name={db_name}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        datasets = response.json()
        if datasets:
            self.dbs[db_name] = datasets["data"][0]["id"]
            logger.debug(f"Database ID for '{db_name}': {self.dbs[db_name]}")
            return datasets["data"][0]["id"]
        else:
            logger.error(f"Database '{db_name}' not found.")

            raise ValueError(f"Database '{db_name}' not found.")

    def retrieve_chunks(
        self,
        query: str,
        db_id: str,
        page_size: int = 10,  # The numner of chunks to retrieve
    ) -> List[Chunk]:
        """
        Retrieve chunks from the RAGFlow database based on a query.
        """
        response = requests.post(
            f"{self.base_url}/api/v1/retrieval",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "question": query,
                "dataset_ids": [db_id],
                "document_ids": [],
                "page_size": page_size,
                "cross_languages": ["German", "English"],
            },
        )
        r = response.json()
        chunks = [Chunk(**chunk) for chunk in r["data"]["chunks"]]
        return chunks
        # return chunks

    def run(self, query: str, db_name: str) -> List[Chunk]:
        """
        Run the retrieval process for a given query and database name.
        """
        chunks = []
        try:
            db_id = self.get_db_id(db_name)
            chunks = self.retrieve_chunks(query, db_id)
            logger.debug(
                f"Retrieved {len(chunks)} chunks for query '{query}' in database '{db_name}'."
            )
        except Exception as e:
            logger.error(f"Error retrieving chunks: {e}")
        return chunks


ragflowretriever = RAGFlowSingleton()


ragflowretriever.run("Credit points computer science", "UOS_PO")
