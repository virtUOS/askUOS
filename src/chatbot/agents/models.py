from typing import NamedTuple

from pydantic import BaseModel, Field


class Reference(BaseModel):
    source: str
    page: int | None = None
    doc_id: str | None = None
    # TODO Delete once metadata is added to RAGFlow API (user to reference FAQ source)
    url_reference_askuos: str | None = None


class RetrievalResult(BaseModel):
    result_text: str = Field(description="Retrieved text from a tool", default="")
    reference: list = []
    source_name: str = Field(
        description="Name of the source or collection where the text was retrieved from",
        default="",
    )
    search_query: str
