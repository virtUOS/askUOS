from langchain.pydantic_v1 import BaseModel, Field


class SearchInputWeb(BaseModel):
    query: str = Field(description="should be a search query")
    about_application: bool = Field(
        description="should be True if the user is inquiring about studying or applying to the university"
    )
    single_subject: bool = Field(
        description="should be True if the user wants to know about study program where students only study one subject (e.g., Biology, Computer Science, Mathematics, Cognitive Sccience, Physics, Psychology, Chemistry, etc.)"
    )
    two_subject: bool = Field(
        description="should be True if the user wants to know about study program where students combine two subjects (e.g.,Core subject (Kernfach)/Core subject (Kernfach): Both subjects have the same number of credit points or Major (Hauptfach)/Minor (Nebenfach): A major has a larger number of credits than the minor."
    )
    teaching_degree: bool = Field(
        description="should be True if the user wants to know about study program where students study to become a teacher (e.g., Lehramt Gymnasium, Lehramt Grundschule, etc.)"
    )


class RetrieverInput(BaseModel):
    """Input to the retriever."""

    query: str = Field(description="query to look up in retriever")
    # TODO make sure that keywords are in German
    filter_program_name: str = Field(
        description="Keyword to filter the documents by study program name, e.g. Biologie, Informatik, Kognitionswissenschaft, Cognitive Science, Chemie, Mathematik, Physik, Psychologie, Wirtschaftsinformatik, Wirtschaftswissenschaften etc."
    )
