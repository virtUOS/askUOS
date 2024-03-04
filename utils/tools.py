# needed generically
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import BaseTool
from utils.search_web_tool import search_uni_web

from typing import Optional, Type

from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)


class SearchInput(BaseModel):
    # todo translage queries to German
    query: str = Field(description="should be a search query")





class CustomSearchTool(BaseTool):
    name = "custom_university_web_search"
    description = """useful for when you need to answer questions about the University of Osnabrück. For example questions about 
    the application process or studying at the university in general. This tool is also useful to access updated application dates
    and updated dates and contact information
    
    """


    args_schema: Type[BaseModel] = SearchInput

    def _run(
        self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        return search_uni_web (query)

    async def _arun(
        self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")


