from langchain.pydantic_v1 import BaseModel, Field


class SearchInputWeb(BaseModel):
    query: str = Field(description="should be a search query")
    about_application: bool = Field(
        description="should be True if the user is inquiring about studying, applying to the university, or asking about specific study options (e.g., 'Can I study history as Hauptfach?', 'What subjects can I combine?', 'How do I apply for Biology?'). This includes questions about study programs, subject combinations, admission requirements, application processes, and general study-related inquiries."
    )
    single_subject: bool = Field(
        description="should be True if the user wants to know about Mono-Bachelor/Fach-Bachelor programs where students focus on only one subject (e.g., Biology, Computer Science, Mathematics, Cognitive Science, Physics, Psychology, Chemistry, etc.). This includes questions like 'Can I study Biology?' or 'What single-subject programs are available?'"
    )
    two_subject: bool = Field(
        description="should be True if the user wants to know about Zwei-Fächer-Bachelor programs where students combine two subjects. This includes both structures: Kernfach/Kernfach combinations (both subjects with equal credit points, e.g., 63 LP each) and Hauptfach/Nebenfach combinations (major with 84 LP, minor with 42 LP). Examples:  'What can I combine with German as Kernfach?', 'Which subjects are available as Nebenfach?'"
    )
    teaching_degree: bool = Field(
        description="should be True if the user wants to know about teacher training programs or study programs that lead to teaching qualifications (e.g., Lehramt Gymnasium, Lehramt Grundschule, Master of Education). This includes questions about becoming a teacher, teaching-related study paths, or educational degree programs."
    )


class RetrieverInput(BaseModel):
    """Input to the retriever."""

    query: str = Field(description="query to look up in retriever")
    # TODO make sure that keywords are in German
    filter_program_name: str = Field(
        description="Keyword to filter the documents by study program name, e.g. Biologie, Informatik, Kognitionswissenschaft, Cognitive Science, Chemie, Mathematik, Physik, Psychologie, Wirtschaftsinformatik, Wirtschaftswissenschaften etc."
    )
