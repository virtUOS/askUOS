from pydantic import BaseModel


class SearchConfig(BaseModel):
    """
    Configuration for the search service.
    """

    search_url: str
    service: str


class ModelConfig(BaseModel):
    """
    Configuration for the model being used.
    """

    model_name: str
    context_window: int  # Number of allowed tokens


class Legal(BaseModel):
    """
    Configuration for legal information.
    """

    data_protection: str
    imprint: str
