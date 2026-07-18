import asyncio
import threading
from urllib.parse import urlparse

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.chatbot.agents.utils.agent_helpers import model_registry
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings


class _SubagentsRegistry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(_SubagentsRegistry, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

    async def create_mcp_clients(self):
        if not self._initialized:
            self._initialized = True
            self.agent_names = []
            self.clients = dict()
            self.extras = dict()

            # this description is used by the task tool
            self.description = """Launch an ephemeral subagent for a task. This tool can be called serveral times to spawn different agents. 
                ### Available agents:
                """
            for i in settings.mcp_agents:
                if i.is_ragflow:
                    parsed = urlparse(i.url)
                    settings.ragflow_reference_url = (
                        f"{parsed.scheme}://{parsed.netloc}"
                    )
                self.agent_names.append(i.agent_name)
                self.extras[i.agent_name] = {
                    "prompt": i.prompt,
                    "is_ragflow": i.is_ragflow,
                }
                self.description += f" - {i.agent_name}: {i.description}\n"
                self.clients[i.agent_name] = MultiServerMCPClient(
                    {
                        i.agent_name: {
                            "transport": i.transport,
                            "url": i.url,
                            "headers": i.headers,
                        },
                    }
                )

    # TODO: DELETE METHOD
    async def create_subagents(self):
        if not self._initialized:
            self._initialized = True
            self.agent_names = []
            self.subagents = dict()
            self.description = """Launch an ephemeral subagent for a task. This tool can be called serveral times to spawn different agents. 
                ### Available agents:
                """
            for i in settings.mcp_agents:

                tools = await i.get_tools()
                self.agent_names.append(i.agent_name)
                self.description += f" - {i.agent_name}: {i.description}\n"
                self.subagents[i.agent_name] = create_agent(
                    model=model_registry.subagent_llm.llm,
                    tools=tools,
                    system_prompt=i.prompt,
                )
                logger.debug(f"Subagent initialized correctly: {i.agent_name}")


subagents_registry = _SubagentsRegistry()
