from typing import List

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config.core_config import settings

if settings.people_search:
    people_search_client = MultiServerMCPClient(
        {
            "people_search": {
                "transport": settings.people_search.transport,  # HTTP-based remote server
                "url": settings.people_search.url,
                "headers": settings.people_search.headers,
            },
        }
    )


if settings.it_services_search:
    it_services_search = MultiServerMCPClient(
        {
            "it_services_search": {
                "transport": settings.it_services_search.transport,  # HTTP-based remote server
                "url": settings.it_services_search.url,
                "headers": settings.it_services_search.headers,
            },
        }
    )
