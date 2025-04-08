from langchain.pydantic_v1 import BaseModel, Field


class SearchInputWeb(BaseModel):
    query: str = Field(description="should be a search query")
    about_application: bool = Field(
        description="should be True if the user is inquiring about studying or applying to the university"
    )


class RetrieverInput(BaseModel):
    """Input to the retriever."""

    query: str = Field(description="query to look up in retriever")
    # TODO make sure that keywords are in German
    filter_program_name: str = Field(
        description="Keyword to filter the documents by study program name, e.g. Biologie, Informatik, Kognitionswissenschaft, Cognitive Science, Chemie, Mathematik, Physik, Psychologie, Wirtschaftsinformatik, Wirtschaftswissenschaften etc."
    )
