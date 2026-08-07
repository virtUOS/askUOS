import asyncio
from enum import Enum
from typing import ClassVar, List, Literal, Optional, Tuple, Type, Union

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel, Field, model_validator


class MsgName(str, Enum):
    further_help = "further_help"


class ToolNames(str, Enum):
    SEARCH_WEB_TOOL = "custom_university_web_search"
    EXAMINATION_REGULATIONS_TOOL = "examination_regulations"
    TROUBLESHOOTING_TOOL = "troubleshooting"
    TASK = "task"


class Languages(str, Enum):
    GERMAN = "Deutsch"
    ENGLISH = "English"


class VectorDBTypes(str, Enum):
    MILVUS = "Milvus"
    INFINITY_RAGFLOW = "Infinity-RAGFlow"


class ProviderNames(str, Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    SELF_HOSTED = "self-hosted"


class RoleNames(str, Enum):
    MAIN = "main"
    HELPER = "helper"
    # Optional dedicated model for ephemeral MCP subagent tool-calling tasks
    # (GraphNodesMixin.task()). If no "subagent" entry is configured, the
    # main model is reused (see _ModelRegistry.create_models), so this is
    # backward compatible with existing configs.
    SUBAGENT = "subagent"


class SearchConfig(BaseModel):
    """
    Configuration for the search service.
    """

    search_url: str
    service: str


class Service(BaseModel):
    """Base class for service configurations"""

    host: str
    port: str
    username: Optional[str] = None
    password: Optional[str] = None


class RedisService(Service):
    """Redis-specific service configuration"""

    ttl_graph_cache: int = (
        120  # how long messages are cached. Msgs older than this value won't be shown to the user
    )
    # Connection pool timeout, in seconds — how long to wait for a
    # connection from the pool / for the connection itself. Was previously
    # a hardcoded timeout=15 in RedisClient.initialize().
    connection_timeout: int = 15

    def build_redis_url(self) -> str:
        """Build Redis connection URL from service settings"""
        if self.password:
            if self.username:
                return (
                    f"redis://{self.username}:{self.password}@{self.host}:{self.port}"
                )
            return f"redis://:{self.password}@{self.host}:{self.port}"
        return f"redis://{self.host}:{self.port}"


class Model(BaseModel):
    """
    Configuration for the model being used.
    """

    provider: ProviderNames
    role: RoleNames
    model_name: str
    base_url: Optional[str] = None
    # LLM client request timeout, in seconds. Was previously a hardcoded
    # timeout=60 at every _build_llm_obj call site regardless of role or
    # provider; now overridable per model entry in backend_config.yaml.
    timeout: int = 60

    @model_validator(mode="after")
    def validate_base_url_for_self_hosted(self):
        """
        Validate that base_url is required when provider is self-hosted.
        """
        if self.provider == ProviderNames.SELF_HOSTED and not self.base_url:
            raise ValueError("base_url is required when provider is 'self-hosted'")
        return self


class ApplicationConfig(BaseModel):
    """
    Configuration for the application.
    """

    debug: bool
    recursion_limit: int = 12
    tracing: bool = False
    opik_project_name: str = "askUOSTesting"
    # Default recursion limit for ephemeral MCP subagents (see MCPAgentConf.
    # recursion_limit for a per-agent override). Kept separate from the main
    # graph's own recursion_limit above since a subagent's tool-calling loop
    # is a different, independently-tunable budget.
    subagent_recursion_limit: int = 10
    # If True, a configured MCP agent that fails its startup connectivity
    # check (see MCPAgentConf.test_connection) aborts application startup
    # entirely. If False (default), the failure is logged loudly but the app
    # still starts — that agent will simply fail gracefully at request time
    # (see GraphNodesMixin.task) instead of blocking deployment.
    fail_on_mcp_unreachable: bool = False
    # Origins allowed to call this API directly from browser-based JS
    # (CORS). Empty by default: no CORSMiddleware is added at all unless at
    # least one origin is configured here, so nothing changes for
    # deployments that don't need this. Only relevant for browser clients
    # calling this API cross-origin (e.g. ui-react running on its own dev
    # server/port, or a chat widget embedded on a different domain) — NOT
    # needed for server-to-server callers (curl, another backend, an
    # external LibreChat-compatible integration), since CORS is a
    # browser-only enforcement mechanism that never applies to direct HTTP
    # client calls.
    cors_allowed_origins: list[str] = Field(default_factory=list)


class EmbeddingSettings(BaseModel):
    """Settings for the self-hosted embedding model (OpenAI-compatible endpoint, e.g. behind LiteLLM)."""

    model_name: str
    base_url: str
    timeout: int = 60


class LogSettings(BaseModel):
    delete_logs_days: int = 90  # Number of days to keep logs before deletion


class MilvusSettings(BaseModel):
    """Settings for Milvus vector database"""

    uri: Optional[str] = "http://localhost:19530"
    host: Optional[str] = None
    port: int = 19530
    token: Optional[str] = "root:Milvus"


class RAGFlowSettings(BaseModel):
    """
    Configuration for RAGFlow settings.
    """

    base_url: str
    chunk_size: int = 10  # Number of chunks to retrieve per request
    # HTTP timeouts (seconds) for the RAGFlow client (RAGFlowSingleton in
    # ragflow_client.py). Previously hardcoded constants at every
    # _get_client() call.
    connect_timeout: float = 15.0  # Time to establish connection
    read_timeout: float = 60.0  # Time to receive response (RAG can be slow)
    write_timeout: float = 15.0  # Time to send request body
    pool_timeout: float = 5.0  # Time waiting for connection from pool


class VectorDBConfig(BaseModel):
    """
    Configuration for the vector database.
    """

    type: VectorDBTypes = VectorDBTypes.MILVUS
    settings: Union[MilvusSettings, RAGFlowSettings]


class CrawlSettings(BaseModel):
    """Settings for web crawler behavior"""

    base_url: str
    crawl_payload: dict  # TODO : requires special validation, use the crawl4ai schema
    ttl_redis: int
    # Max number of web pages visited per search_web_tool call.
    max_links: int = 6


class ExaminationRegulations(BaseModel):
    collection_name: str


class Troubleshooting(BaseModel):
    collection_name: Optional[str] = "troubleshooting"
    activate: bool = False
    description: str = ""


class FaqSettings(BaseModel):
    activate: bool = False
    collection_name: Optional[str] = "faq"


class GraphConfig(BaseModel):
    # summarize if context is >= summary_threshold
    summary_threshold: int
    faq: FaqSettings
    troubleshooting: Troubleshooting
    # Skip grade_documents' LLM relevance call entirely when this turn's tool
    # results came only from high-trust structured sources (RAGFlow/FAQ).
    skip_grading_for_high_trust_sources: bool = False
    # Embedding-similarity pre-filter thresholds for grade_documents, used on
    # the remaining (non-high-trust) path. None disables the pre-filter.
    # Similarity >= high routes straight to generate; <= low routes straight
    # to rewrite; anything in between still falls through to the LLM grader.
    embedding_prefilter_high_threshold: Optional[float] = None
    embedding_prefilter_low_threshold: Optional[float] = None
    # Max input context (in tokens) of the embedding model configured under
    # `embedding:` (e.g. BGE-M3 supports up to 8192). grade_documents converts
    # this into a character budget via a rough chars-per-token estimate (see
    # _EMBEDDING_CHARS_PER_TOKEN_ESTIMATE in graph_node_edges.py) since exact
    # tokenization isn't available for the self-hosted embedding model.
    embedding_prefilter_max_context_tokens: int = 8192


class Message(BaseModel):
    msg_name: MsgName
    english: str
    german: str


class MCPAgentConf(BaseModel):
    transport: Literal["stdio", "sse", "http"]
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    # Recursion limit for this subagent's own tool-calling loop (separate
    # from the main graph's ApplicationConfig.recursion_limit).
    recursion_limit: Optional[int] = 8
    # Optional wall-clock timeout (seconds) for a single subagent invocation,
    # so one hung MCP tool can't stall the whole user turn indefinitely.
    timeout_seconds: Optional[float] = None
    agent_name: str  # each mcp is connected to a retriaval agent. The agent name should be telling. As the name is also passed to the LLM.
    prompt: Optional[str] = None  # it is passed to the agent
    description: str  # Tells the routing agent (main agent) when to use this mcp/agent (it is not a tool decription)
    is_ragflow: bool = (
        False  # Ragflow mcp has better support e.g., references are parsed and added to final answer
    )
    enabled: bool = (
        True  # Set to False to keep a config block without activating it (e.g. during rollout/testing)
    )

    async def test_connection(self) -> int:
        """Attempt to connect to the configured MCP server and list its tools.

        Returns the number of tools found on success. Raises RuntimeError on
        any failure (unreachable host, bad auth headers, wrong transport,
        etc.) so callers can decide how strictly to react.
        """
        client = MultiServerMCPClient(
            {
                self.agent_name: {
                    "transport": self.transport,
                    "url": self.url,
                    "headers": self.headers,
                },
            }
        )

        try:
            async with client.session(self.agent_name) as session:
                tools = await session.list_tools()
            # session.list_tools() (the mcp SDK's ClientSession) returns a
            # ListToolsResult object with a .tools list attribute, not a bare
            # list — len(tools) directly raises TypeError, which the except
            # below previously mislabeled as a connection failure even
            # though the connection and the call both succeeded. Some
            # wrappers may already hand back a plain list, so fall back to
            # the value itself if there's no .tools attribute.
            tool_list = getattr(tools, "tools", tools)
            return len(tool_list)
        except Exception as e:
            raise RuntimeError(
                f"MCP connection failed for '{self.agent_name}': {e}"
            ) from e

    async def get_tools(self):
        client = MultiServerMCPClient(
            {
                self.agent_name: {
                    "transport": self.transport,
                    "url": self.url,
                    "headers": self.headers,
                },
            }
        )
        # Connection to the mcp is tested here
        tools = await client.get_tools()
        return tools
