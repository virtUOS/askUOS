# code taking from langchain.tools.retriever. The code is modified to return the references of the documents

from __future__ import annotations

from functools import partial
from typing import Optional

from langchain.tools import BaseTool
from langchain_core.callbacks import Callbacks
from langchain_core.prompts import PromptTemplate, format_document
from langchain_core.pydantic_v1 import BaseModel, Field

from src.chatbot.db.clients import get_retriever
from src.chatbot.tools.utils.tool_helpers import visited_docs


class RetrieverInput(BaseModel):
    """Input to the retriever."""

    query: str = Field(description="query to look up in retriever")
    # TODO make sure that keywords are in German
    filter_program_name: str = Field(
        description="Keyword to filter the documents by program name, e.g. Biologie, Informatik, Kognitionswissenschaft "
    )


def _get_relevant_documents(
    query: str,
    filter_program_name: str,
) -> str:
    # TODO: add a filter for the program name WHEN searching
    document_separator = "\n\n"
    document_prompt = PromptTemplate.from_template("{page_content}")
    retriever = retriever = get_retriever("examination_regulations")

    docs = retriever.invoke(query)

    results = []
    # example {'pk': 'f707471d-7369-43e0-a94a-4293', 'source': 'data/documents/PVO-10-31.pdf', 'page': 38}

    for doc in docs:
        # TODO consider moving this to the graph state
        visited_docs().append(doc.metadata)
        results.append(format_document(doc, document_prompt))

    return document_separator.join(results)
