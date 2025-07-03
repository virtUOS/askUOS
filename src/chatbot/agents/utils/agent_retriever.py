# code taking from langchain.tools.retriever. The code is modified to return the references of the documents

from __future__ import annotations

from langchain_core.prompts import PromptTemplate, format_document

from src.chatbot.db.clients import get_milvus_client
from src.chatbot.tools.utils.tool_helpers import visited_docs
from src.chatbot_log.chatbot_logger import logger

# TODO: REFACTOR EVERYTHING INTO ONE FUNCTION

HIS_IN_ONE_COLLECTON = "troubleshooting"
EXAMINATION_REGULATIONS_COLLECTION = "examination_regulations"
DOCUMENT_SEPARATOR = "\n\n"
DOCUMENT_PROMPT = PromptTemplate.from_template("{page_content}")
NOT_FOUND_MESSAGE = "Result: No documents found"


def _get_relevant_documents(
    query: str,
    filter_program_name: str,
) -> str:
    # TODO: add a filter for the program name WHEN searching

    vector_store = get_milvus_client(EXAMINATION_REGULATIONS_COLLECTION)
    if vector_store is None:
        logger.error(
            f"[VECTOR DB]Failed to get Milvus client for collection: {EXAMINATION_REGULATIONS_COLLECTION}"
        )
        return NOT_FOUND_MESSAGE

    try:
        docs = vector_store.similarity_search(
            query, expr=f"source LIKE '%{filter_program_name}%'", k=5
        )

        results = []
        # example {'pk': 'f707471d-7369-43e0-a94a-4293', 'source': 'data/documents/PVO-10-31.pdf', 'page': 38}

        for doc in docs:
            # TODO consider moving this to the graph state
            visited_docs().append(doc.metadata)
            results.append(format_document(doc, DOCUMENT_PROMPT))

        return DOCUMENT_SEPARATOR.join(results)
    except Exception as e:
        logger.error(f"[VECTOR DB]Error during similarity search: {e}")
        return NOT_FOUND_MESSAGE


def retriever_his_in_one(query: str) -> str:

    vector_store = get_milvus_client(HIS_IN_ONE_COLLECTON)
    if vector_store is None:
        logger.error(
            f"[VECTOR DB]Failed to get Milvus client for collection: {HIS_IN_ONE_COLLECTON}"
        )
        return NOT_FOUND_MESSAGE

    try:
        docs = vector_store.similarity_search(query, k=5)

        results = []

        for doc in docs:

            results.append(format_document(doc, DOCUMENT_PROMPT))

        return DOCUMENT_SEPARATOR.join(results)

    except Exception as e:
        logger.error(f"[VECTOR DB]Error during similarity search: {e}")
        return NOT_FOUND_MESSAGE
