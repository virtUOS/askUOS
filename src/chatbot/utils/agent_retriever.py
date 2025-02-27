# code taking from langchain.tools.retriever. The code is modified to return the references of the documents

from __future__ import annotations

from functools import partial
from typing import Optional

from langchain.tools import BaseTool
from langchain_core.callbacks import Callbacks
from langchain_core.prompts import PromptTemplate, format_document
from langchain_core.pydantic_v1 import BaseModel, Field

from src.chatbot.db.clients import get_milvus_client, get_retriever
from src.chatbot.tools.utils.tool_helpers import visited_docs


class RetrieverInput(BaseModel):
    """Input to the retriever."""

    query: str = Field(description="query to look up in retriever")
    # TODO make sure that keywords are in German
    filter_program_name: str = Field(
        description="Keyword to filter the documents by study program name, e.g. Biologie, Informatik, Kognitionswissenschaft, Cognitive Science, Chemie, Mathematik, Physik, Psychologie, Wirtschaftsinformatik, Wirtschaftswissenschaften etc."
    )


def _get_relevant_documents(
    query: str,
    filter_program_name: str,
) -> str:
    # TODO: add a filter for the program name WHEN searching
    document_separator = "\n\n"
    document_prompt = PromptTemplate.from_template("{page_content}")
    # retriever = retriever = get_retriever("examination_regulations")
    vector_store = get_milvus_client("examination_regulations")

    # docs = retriever.invoke(query)
    docs = vector_store.similarity_search(
        query, expr=f"source LIKE '%{filter_program_name}%'", k=5
    )

    results = []
    # example {'pk': 'f707471d-7369-43e0-a94a-4293', 'source': 'data/documents/PVO-10-31.pdf', 'page': 38}

    for doc in docs:
        # TODO consider moving this to the graph state
        visited_docs().append(doc.metadata)
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
