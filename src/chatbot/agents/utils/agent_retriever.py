import os

from src.chatbot.db.clients import milvus_client
from src.chatbot.embeddings.main import get_embeddings
from src.chatbot.tools.utils.tool_helpers import visited_docs
from src.chatbot_log.chatbot_logger import logger

HIS_IN_ONE_COLLECTON = "troubleshooting"
EXAMINATION_REGULATIONS_COLLECTION = "examination_regulations"
DOCUMENT_SEPARATOR = "\n\n"
NOT_FOUND_MESSAGE = "Result: No documents found"

search_params = {
    "metric_type": "L2",
    "offset": 0,
    "ignore_growing": False,
    "params": {"nprobe": 10},
}


def _get_relevant_documents(
    query: str,
    filter_program_name: str,
) -> str:
    # TODO: add a filter for the program name WHEN searching

    try:

        # test if the collection is loaded
        loaded = milvus_client.client.get_load_state(
            collection_name=EXAMINATION_REGULATIONS_COLLECTION
        )
        if loaded["state"].name != "Loaded":
            logger.warning(
                f"[VECTOR DB]Collection {EXAMINATION_REGULATIONS_COLLECTION} is not loaded. Current state: {loaded}"
            )

        # get query vector
        query_vector = get_embeddings(query)

        docs = milvus_client.client.search(
            collection_name=EXAMINATION_REGULATIONS_COLLECTION,
            output_fields=["pk", "source", "text", "page"],
            data=[query_vector],
            search_params=search_params,
            filter=f"source LIKE '%{filter_program_name}%'",
        )

        results = []

        # TODO: IMPLEMENT A RERANKING FUNCTION
        for doc in docs[0]:
            # TODO consider moving this to the graph state
            source = os.path.basename(doc["entity"]["source"])
            page = doc["entity"]["page"]
            visited_docs().append((source, page))
            results.append(f'Source: {source} \nText: {doc["entity"]["text"]}')

        return DOCUMENT_SEPARATOR.join(results)
    except Exception as e:
        logger.error(f"[VECTOR DB]Error during similarity search: {e}")
        return NOT_FOUND_MESSAGE


def retriever_his_in_one(query: str) -> str:

    # test if the collection is loaded
    loaded = milvus_client.client.get_load_state(collection_name=HIS_IN_ONE_COLLECTON)
    if loaded["state"].name != "Loaded":
        logger.warning(
            f"[VECTOR DB]Collection {HIS_IN_ONE_COLLECTON} is not loaded. Current state: {loaded}"
        )

    try:
        # get query vector
        query_vector = get_embeddings(query)

        docs = milvus_client.client.search(
            collection_name=HIS_IN_ONE_COLLECTON,
            output_fields=["pk", "text"],
            data=[query_vector],
            search_params=search_params,
        )

        results = []

        for doc in docs[0]:

            results.append(doc["entity"]["text"])

        return DOCUMENT_SEPARATOR.join(results)

    except Exception as e:
        logger.error(f"[VECTOR DB]Error during similarity search: {e}")
        return NOT_FOUND_MESSAGE
