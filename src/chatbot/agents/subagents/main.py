import asyncio
import logging
import threading
from urllib.parse import urlparse

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.chatbot_log.chatbot_logger import log_event, logger
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
        # Baseline empty state so attributes like `agent_names` are always
        # safe to read (e.g. from GraphNodesMixin.create_tools()) even when
        # settings.mcp_agents is empty/None and create_mcp_clients() is never
        # called at all.
        self.agent_names = []
        self.clients = dict()
        self.extras = dict()
        self.description = ""

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
            active_agents = [i for i in settings.mcp_agents if i.enabled]
            skipped = len(settings.mcp_agents) - len(active_agents)
            if skipped:
                logger.info(
                    f"[MCP] Skipping {skipped} disabled MCP agent(s) (enabled: False in config)"
                )

            for i in active_agents:

                self.agent_names.append(i.agent_name)
                self.extras[i.agent_name] = {
                    "prompt": i.prompt,
                    "is_ragflow": i.is_ragflow,
                    "recursion_limit": i.recursion_limit
                    or settings.application.subagent_recursion_limit,
                    "timeout_seconds": i.timeout_seconds,
                }
                if i.is_ragflow:
                    parsed = urlparse(i.url)
                    self.extras[i.agent_name][
                        "reference_url"
                    ] = f"{parsed.scheme}://{parsed.netloc}"

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

            await self._check_mcp_connectivity(active_agents)

    async def _check_mcp_connectivity(self, active_agents: list) -> None:
        """Verify every enabled MCP agent is actually reachable at startup.

        Logs a structured MCP_STARTUP_CHECK event per agent (ok/failure,
        tool count or error). If settings.application.fail_on_mcp_unreachable
        is True, an unreachable agent aborts application startup entirely;
        otherwise the failure is logged loudly and the app still starts —
        that agent will simply fail gracefully at request time instead
        (see GraphNodesMixin.task).
        """
        if not active_agents:
            return

        results = await asyncio.gather(
            *(i.test_connection() for i in active_agents), return_exceptions=True
        )

        unreachable = []
        for agent_conf, result in zip(active_agents, results):
            if isinstance(result, Exception):
                unreachable.append(agent_conf.agent_name)
                log_event(
                    "MCP_STARTUP_CHECK",
                    "MCP agent unreachable at startup",
                    level=logging.ERROR,
                    agent_name=agent_conf.agent_name,
                    ok=False,
                    error=str(result),
                )
            else:
                log_event(
                    "MCP_STARTUP_CHECK",
                    "MCP agent reachable",
                    agent_name=agent_conf.agent_name,
                    ok=True,
                    tool_count=result,
                )

        if unreachable and settings.application.fail_on_mcp_unreachable:
            raise RuntimeError(
                f"MCP startup connectivity check failed for: {', '.join(unreachable)}. "
                "Set application.fail_on_mcp_unreachable: false to start anyway."
            )


subagents_registry = _SubagentsRegistry()
