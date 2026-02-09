import asyncio
import os
from typing import List, NamedTuple

from pydantic import BaseModel

from src.chatbot.agents.models import Reference, RetrievalResult
from src.chatbot.db.ragflow_client import ragflow_object
from src.chatbot.embeddings.main import get_embeddings
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings
from src.config.models import CollectionNames, VectorDBTypes

DOCUMENT_SEPARATOR = "\n\n"
NOT_FOUND_MESSAGE = "Result: No documents found"

# TODO: Rewrite this module, provide an API to retrieve using Milvus or Infinity

VECTOR_DB_TYPE = settings.vector_db_settings.type


async def retrieve_from_infinity_ragflow(
    collection_name: str, query: str
) -> RetrievalResult:
    ref: list[Reference] = []
    results = []
    try:

        retrieved = await ragflow_object.get_chunks(query, collection_name)
        for retrieved_item in retrieved:
            source = retrieved_item.chunk.document_keyword
            page = retrieved_item.chunk.page
            ref.append(
                Reference(
                    source=source,
                    page=page,
                    doc_id=retrieved_item.chunk.document_id,
                    url_reference_askuos=retrieved_item.chunk.url_reference_askuos,
                )
            )
            results.append(f"Source: {source} \nText: {retrieved_item.chunk.content}")
        return RetrievalResult(
            result_text=DOCUMENT_SEPARATOR.join(results),
            reference=ref,
            source_name=collection_name,
            search_query=query,
        )

    except Exception as e:
        logger.error(f"[RAGFlow]Error during similarity search: {e}")
        return RetrievalResult(
            result_text=NOT_FOUND_MESSAGE,
            reference=ref,
            source_name=collection_name,
            search_query=query,
        )


def retrieve_from_milvus(collection_name: str, query: str, doc_search_params: dict):

    from src.chatbot.db.milvus_client import MilvusSingleton

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
                f"[VECTOR DB][MILVUS]Collection {collection_name} is not loaded. Current state: {loaded}"
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
        logger.error(f"[VECTOR DB][MILVUS]Error during similarity search: {e}")
        raise e


# used by the examination regulations tool


async def _examination_regulations_tool(
    **kwargs,
) -> RetrievalResult:
    # TODO: add a filter for the program name WHEN searching
    query = kwargs.get("query", "")
    filter_program_name = kwargs.get("filter_program_name", "")
    ref: list[Reference] = []
    results = []
    # TODO: Needs asyn implementation
    if VECTOR_DB_TYPE == VectorDBTypes.MILVUS:

        try:
            doc_search_params = {
                "output_fields": ["pk", "source", "text", "page"],
                "filter": f"source LIKE '%{filter_program_name}%'",
            }

            docs = retrieve_from_milvus(
                CollectionNames.EXAMINATION_REGULATIONS, query, doc_search_params
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
    elif VECTOR_DB_TYPE == VectorDBTypes.INFINITY_RAGFLOW:
        query = f"{query}  {filter_program_name if filter_program_name else ''}"
        return await retrieve_from_infinity_ragflow(
            CollectionNames.EXAMINATION_REGULATIONS.value, query
        )
    else:
        logger.error(f"[VECTOR DB]Unsupported vector DB type: {VECTOR_DB_TYPE}")
        return NOT_FOUND_MESSAGE, ref


# used by the hisinone tool
async def _retriever_his_in_one_tool(**kwargs) -> str:

    query = kwargs.get("query", "")
    if VECTOR_DB_TYPE == VectorDBTypes.MILVUS:
        try:

            doc_search_params = {
                "output_fields": ["pk", "text"],
            }

            results = []

            docs = retrieve_from_milvus(
                CollectionNames.TROUBLESHOOTING, query, doc_search_params
            )

            for doc in docs[0]:

                results.append(doc["entity"]["text"])

            return DOCUMENT_SEPARATOR.join(results)

        except Exception as e:
            return NOT_FOUND_MESSAGE
    elif VECTOR_DB_TYPE == VectorDBTypes.INFINITY_RAGFLOW:

        return await retrieve_from_infinity_ragflow(
            CollectionNames.TROUBLESHOOTING.value, query
        )
    else:
        logger.error(f"[VECTOR DB]Unsupported vector DB type: {VECTOR_DB_TYPE}")
        return NOT_FOUND_MESSAGE
