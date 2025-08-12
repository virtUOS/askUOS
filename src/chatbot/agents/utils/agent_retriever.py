import os
from typing import List, NamedTuple

from src.chatbot.db.milvus_client import MilvusSingleton
from src.chatbot.db.ragflow_client import RAGFlowSingleton
from src.chatbot.embeddings.main import get_embeddings
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

HIS_IN_ONE_COLLECTON = "troubleshooting"
EXAMINATION_REGULATIONS_COLLECTION = "examination_regulations"
DOCUMENT_SEPARATOR = "\n\n"
NOT_FOUND_MESSAGE = "Result: No documents found"


# TODO: Rewrite this module, provide an API to retrieve using Milvus or Infinity

VECTOR_DB_TYPE = settings.vector_db_settings.type


class Reference(NamedTuple):
    source: str
    page: int
    doc_id: str | None = None


def retrieve_from_infinity_ragflow(collection_name: str, query: str):
    ref: list[Reference] = []
    results = []
    try:

        ragflow_client = RAGFlowSingleton()
        chunks = ragflow_client.get_chunks(query, collection_name)
        for chunk in chunks:
            source = chunk.document_keyword
            page = chunk.page
            ref.append(Reference(source, page, chunk.document_id))
            results.append(f"Source: {source} \nText: {chunk.content}")
        return DOCUMENT_SEPARATOR.join(results), ref
    except Exception as e:
        logger.error(f"[RAGFlow]Error during similarity search: {e}")
        return NOT_FOUND_MESSAGE, ref


def retrieve_from_milvus(collection_name: str, query: str, doc_search_params: dict):

    search_params = {
        "metric_type": "L2",
        "offset": 0,
        "ignore_growing": False,
        "params": {"nprobe": 10},
    }
    milvus_client = MilvusSingleton()
    try:

        # test if the collection is loaded
        loaded = milvus_client.client.get_load_state(collection_name=collection_name)
        if loaded["state"].name != "Loaded":
            logger.warning(
                f"[VECTOR DB]Collection {collection_name} is not loaded. Current state: {loaded}"
            )

        # get query vector
        query_vector = get_embeddings(query)

        docs = milvus_client.client.search(
            collection_name=collection_name,
            data=[query_vector],
            search_params=search_params,
            **doc_search_params,
        )
        return docs
    except Exception as e:
        logger.error(f"[VECTOR DB]Error during similarity search: {e}")
        raise e


# used by the examination regulations tool
def _get_relevant_documents(
    query: str,
    filter_program_name: str,
) -> tuple[str, list[Reference]]:
    # TODO: add a filter for the program name WHEN searching

    ref: list[Reference] = []
    results = []

    if VECTOR_DB_TYPE == "Milvus":

        try:
            doc_search_params = {
                "output_fields": ["pk", "source", "text", "page"],
                "filter": f"source LIKE '%{filter_program_name}%'",
            }

            docs = retrieve_from_milvus(
                EXAMINATION_REGULATIONS_COLLECTION, query, doc_search_params
            )
            # TODO: IMPLEMENT A RERANKING FUNCTION

            for doc in docs[0]:
                # TODO consider moving this to the graph state
                source = os.path.basename(doc["entity"]["source"])
                page = doc["entity"]["page"]
                ref.append(Reference(source, page))
                results.append(f'Source: {source} \nText: {doc["entity"]["text"]}')

            return DOCUMENT_SEPARATOR.join(results), ref
        except Exception as e:
            return NOT_FOUND_MESSAGE, ref
    elif VECTOR_DB_TYPE == "Infinity-RAGFlow":

        return retrieve_from_infinity_ragflow(EXAMINATION_REGULATIONS_COLLECTION, query)
    else:
        logger.error(f"[VECTOR DB]Unsupported vector DB type: {VECTOR_DB_TYPE}")
        return NOT_FOUND_MESSAGE, ref


# used by the hisinone tool
def retriever_his_in_one(query: str) -> str:

    try:

        doc_search_params = {
            "output_fields": ["pk", "text"],
        }

        results = []

        docs = retrieve_from_milvus(HIS_IN_ONE_COLLECTON, query, doc_search_params)

        for doc in docs[0]:

            results.append(doc["entity"]["text"])

        return DOCUMENT_SEPARATOR.join(results)

    except Exception as e:
        return NOT_FOUND_MESSAGE
