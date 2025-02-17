# code taking from langchain.tools.retriever

from __future__ import annotations

from functools import partial
from typing import Optional

from langchain.tools.retriever import RetrieverInput
from langchain_core.callbacks import Callbacks
from langchain_core.prompts import BasePromptTemplate, PromptTemplate, format_document
from langchain_core.retrievers import BaseRetriever
from langchain_core.tools.simple import Tool


def _get_relevant_documents(
    query: str,
    retriever: BaseRetriever,
    document_prompt: BasePromptTemplate,
    document_separator: str,
    callbacks: Callbacks = None,
) -> str:
    docs = retriever.invoke(query, config={"callbacks": callbacks})

    results = []
    # example {'pk': 'f707471d-7369-43e0-a94a-4293', 'source': 'data/documents/PVO-10-31.pdf', 'page': 38}
    references = []
    for doc in docs:
        references.append(doc.metadata)
        results.append(format_document(doc, document_prompt))

    return {
        "retrieved_content": document_separator.join(results),
        "references": references,
    }


def create_retriever_tool(
    retriever: BaseRetriever,
    name: str,
    description: str,
    *,
    document_prompt: Optional[BasePromptTemplate] = None,
    document_separator: str = "\n\n",
) -> Tool:
    """Create a tool to do retrieval of documents.

    Args:
        retriever: The retriever to use for the retrieval
        name: The name for the tool. This will be passed to the language model,
            so should be unique and somewhat descriptive.
        description: The description for the tool. This will be passed to the language
            model, so should be descriptive.
        document_prompt: The prompt to use for the document. Defaults to None.
        document_separator: The separator to use between documents. Defaults to "\n\n".

    Returns:
        Tool class to pass to an agent.
    """
    document_prompt = document_prompt or PromptTemplate.from_template("{page_content}")
    func = partial(
        _get_relevant_documents,
        retriever=retriever,
        document_prompt=document_prompt,
        document_separator=document_separator,
    )

    return Tool(
        name=name,
        description=description,
        func=func,
        args_schema=RetrieverInput,
    )
