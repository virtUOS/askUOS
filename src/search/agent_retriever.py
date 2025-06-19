# code taking from langchain.tools.retriever. The code is modified to return the references of the documents

from __future__ import annotations

from functools import partial
from typing import Any, List, Optional

from langchain.tools import BaseTool
from langchain_core.callbacks import Callbacks
from langchain_core.prompts import PromptTemplate, format_document
from langchain_core.pydantic_v1 import BaseModel, Field

from src.chatbot.db.clients import get_milvus_client, get_retriever
from src.chatbot.tools.utils.tool_helpers import visited_docs
from src.chatbot.tools.utils.tool_schema import RetrieverInput
from src.chatbot_log.chatbot_logger import logger


def _get_relevant_documents(
    primary_query: str,
    alternative_query: str,
    # broader_query: str,
    entities: List[str],
    filter_program_name: str,
    hypothetical_answer: str,
) -> str:
    """Get relevant documents using multiple search strategies."""
    document_separator = "\n\n"
    document_prompt = PromptTemplate.from_template("{page_content}")
    vector_store = get_milvus_client("examination_regulations")

    # TODO: This filter excludes the general regulations and focuses on specific programs.
    # Prepare filter expression
    filter_expr = f"source LIKE '%{filter_program_name}%'"

    # Collect all unique documents from multiple queries
    all_docs = []
    seen_doc_ids = set()

    # TODO: Implement a reranker to improve the quality of the results
    # Search with primary query
    primary_docs = vector_store.similarity_search(primary_query, expr=filter_expr, k=3)
    for doc in primary_docs:
        doc_id = doc.metadata.get("pk", "")
        if doc_id not in seen_doc_ids:
            all_docs.append(doc)
            seen_doc_ids.add(doc_id)

    # Search with alternative query if provided
    if alternative_query:
        alt_docs = vector_store.similarity_search(
            alternative_query, expr=filter_expr, k=2
        )
        for doc in alt_docs:
            doc_id = doc.metadata.get("pk", "")
            if doc_id not in seen_doc_ids:
                all_docs.append(doc)
                seen_doc_ids.add(doc_id)

    # Search with broader query
    # broader_docs = vector_store.similarity_search(broader_query, expr=filter_expr, k=2)
    # for doc in broader_docs:
    #     doc_id = doc.metadata.get("pk", "")
    #     if doc_id not in seen_doc_ids:
    #         all_docs.append(doc)
    #         seen_doc_ids.add(doc_id)

    hypothetical_docs = vector_store.similarity_search(
        hypothetical_answer, expr=filter_expr, k=2
    )
    for doc in hypothetical_docs:
        doc_id = doc.metadata.get("pk", "")
        if doc_id not in seen_doc_ids:
            all_docs.append(doc)
            seen_doc_ids.add(doc_id)

    results = []
    for doc in all_docs:
        # Track visited documents
        visited_docs().append(doc.metadata)
        logger.debug(f"{doc.metadata.get('source', '')}-{doc.metadata.get('page', '')}")
        results.append(format_document(doc, document_prompt))

    return document_separator.join(results)


# docs = retriever.invoke("master thesis biology", filter={'source like "Economics"'})


# client.describe_collection(collection_name='examination_regulations')
# {'collection_name': 'examination_regulations',
#  'auto_id': False, 'num_shards': 1, 'description': '',
#  'fields': [{'field_id': 100, 'name': 'text', 'description': '', 'type': <DataType.VARCHAR: 21>, 'params': {'max_length': 65535}},
#             {'field_id': 101, 'name': 'pk', 'description': '', 'type': <DataType.VARCHAR: 21>, 'params': {'max_length': 65535}, 'is_primary': True},
#             {'field_id': 102, 'name': 'vector', 'description': '', 'type': <DataType.FLOAT_VECTOR: 101>, 'params': {'dim': 1024}},
#             {'field_id': 103, 'name': 'source', 'description': '', 'type': <DataType.VARCHAR: 21>, 'params': {'max_length': 65535}},
#             {'field_id': 104, 'name': 'page', 'description': '', 'type': <DataType.INT64: 5>, 'params': {}}],
#  'functions': [], 'aliases': [], 'collection_id': 456074387336045529, 'consistency_level': 1, 'properties': {}, 'num_partitions': 1, 'enable_dynamic_field': False}

# data/documents/Modulbeschreibungen_ConflictStudiesPeacebuilding_EN_2021-03.pdf
