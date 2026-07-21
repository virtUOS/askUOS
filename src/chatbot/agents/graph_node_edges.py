import asyncio
import json
import logging
import os
import pdb
import traceback
from collections import deque
from typing import Annotated, ClassVar, Dict, List, Literal, Optional, Union
from urllib.parse import urlparse

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import RemoveMessage
from langchain_classic.tools import StructuredTool
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import PromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import RemoveMessage, add_messages
from pydantic import BaseModel, Field, create_model
from typing_extensions import TypedDict

from src.chatbot.agents.models import Reference, RetrievalResult, RetrievalToolType
from src.chatbot.agents.subagents.main import subagents_registry
from src.chatbot.agents.utils.agent_helpers import model_registry
from src.chatbot.agents.utils.agent_retriever import (
    _examination_regulations_tool,
    _retriever_his_in_one_tool,
    retrieve_from_infinity_ragflow,
)
from src.chatbot.agents.utils.exceptions import MustContainSystemMessageException
from src.chatbot.prompt.internal_prompt_text import translate_internal_string
from src.chatbot.prompt.main import get_system_prompt, translate_prompt
from src.chatbot.tools.utils.tool_helpers import ReferenceRetriever
from src.chatbot.tools.utils.tool_schema import (
    AgentRetrievedResult,
    HisInOneInput,
    RetrieverInput,
    SearchInputWeb,
    TaskInput,
)
from src.chatbot_log.chatbot_logger import log_event, logger
from src.config.core_config import settings
from src.config.models import ToolNames, VectorDBTypes

# Importat when it comes to models with restricted context window
MESSAGE_HISTORY_LIMIT = 7


# TODO Verify if this step is necessary
def _sanitize_ai_message(message: AIMessage) -> AIMessage:
    """Strip non-serializable metadata."""
    try:
        return AIMessage(
            content=message.content,
            tool_calls=message.tool_calls or [],
            additional_kwargs=message.additional_kwargs or {},
            id=message.id,
        )
    except Exception as e:

        logger.error(
            f"[LLM-OPERATION] Model answer could not be mapped to AIMessage: {e}"
        )
        raise


def add_lists(existing: list, new: list) -> list:
    """Reducer that accumulates list items across nodes."""
    return existing + new


def add(left, right):
    """Reducer"""
    return left + right


class State(TypedDict):
    """State management for the graph-based agent.

    Attributes:

        messages: List of messages in the conversation
        search_query: Optional list of queries used for web/db searches
        user_initial_query: Optional string containing the user's initial query
        answer_rejection: Optional string for rejected answers
        score_judgement_binary: Optional string for binary judgement scores
    """

    # the ai and human messages contained here are also shown to the user.
    messages: Annotated[list[BaseMessage], add_messages]
    user_message_history: Annotated[List[dict], add]
    search_query: Optional[List[str]]
    user_initial_query: Optional[str]
    current_date: Optional[str]
    answer_rejection: Optional[str]
    score_judgement_binary: Optional[str]
    about_application: Optional[
        bool
    ]  # To determine which node generates the answer (!!!set to False when invoking graph)
    teaching_degree: Optional[
        bool
    ]  # To determine which node generates the answer  (!!!set to False when invoking graph)
    tool_messages: Optional[str]
    last_tool_usage: Optional[dict]
    rewrite_query: bool  # Flag to indicate if the query should be rewritten (!!!set to False when invoking graph)
    # ---- Per-request references----
    visited_links: Annotated[list[str], add_lists]
    doc_references: Annotated[list, add_lists]  # list of doc reference objects
    language: Optional[str]  # Literal["Deutsch", "English"]


class GraphNodesMixin:
    """Mixin class handling node operations in the graph."""

    def _extract_tool_info(self, retrieval_result: List[RetrievalResult]):
        outputs_txt = ""
        search_query = []
        new_links = []
        new_doc_refs = []

        if retrieval_result:
            for result in retrieval_result:
                # For general mcps, this should return a doc_reference markdown link

                if isinstance(result, Exception):
                    logger.error(f"Tool call failed: {result}")
                    continue
                if result.source_name == settings.graph.faq.collection_name:
                    unique_refs = {
                        item.url_reference_askuos for item in result.reference
                    }
                    new_links.extend(unique_refs)
                elif result.retrieval_tool == RetrievalToolType.RAGFLOW.value:

                    new_doc_refs.extend(result.reference)

                # web search
                elif result.retrieval_tool == RetrievalToolType.WEB_SEARCH.value:
                    new_links.extend(result.reference)

                elif result.retrieval_tool == RetrievalToolType.UNKNOWN.value:
                    pass

                outputs_txt += result.result_text + "\n\n"
                search_query.append(result.search_query)

            return outputs_txt, search_query, new_links, new_doc_refs
        return "No content found", search_query, new_links, new_doc_refs

    @staticmethod
    def extract_ragflow_chunks(
        chunks: list, url_reference: str = None, query: str = None
    ):
        DOCUMENT_SEPARATOR = "\n\n"
        results = []
        ref = []

        for retrieved_item in chunks:
            source = retrieved_item["document_keyword"]
            page = (
                retrieved_item["positions"][0][0] if retrieved_item["positions"] else 0
            )

            RAGFLOW_BETA_TOKEN = os.getenv("RAGFLOW_BETA_TOKEN", "")
            ragflow_link = "{}/document/{}?ext=pdf&prefix=document&auth={}"
            ref.append(
                Reference(
                    source=source,
                    page=page,
                    doc_id=retrieved_item["document_id"],
                    url_reference_askuos=ragflow_link.format(
                        url_reference,
                        retrieved_item["document_id"],
                        RAGFLOW_BETA_TOKEN,
                    ),  # references are done in fastapi
                )
            )
            results.append(f"Source: {source} \nText: {retrieved_item['content']}")
        # Frontend endpoint https://ragflow.de/document/541adbd59f694d86277375f17b9b4306?ext=pdf&prefix=document&auth=beta_token
        # Backed endpoint https://ragflow.de/api/v1/documents/doc_id/preview
        return RetrievalResult(
            result_text=DOCUMENT_SEPARATOR.join(results),
            reference=ref,
            source_name=retrieved_item["dataset_name"],
            search_query=query,
            retrieval_tool=RetrievalToolType.RAGFLOW,
        )

    @staticmethod
    def _no_info_result(task_description: str) -> RetrievalResult:

        return RetrievalResult(
            result_text="No information retrieved that could answer/solve the user's query",
            search_query=task_description,
            retrieval_tool=RetrievalToolType.UNKNOWN,
        )

    @staticmethod
    def _describe_exception(e: BaseException, _depth: int = 0) -> str:
        """Render an exception for logging, unwrapping ExceptionGroup/
        TaskGroup wrappers so the *actual* underlying failure is visible.

        The MCP client session (anyio/asyncio TaskGroup under the hood)
        wraps any real failure (connection refused, DNS failure, auth
        rejected, bad transport, etc.) in a generic
        "unhandled errors in a TaskGroup (N sub-exception(s))" message with
        no detail of its own — str(e) on that wrapper is useless for
        diagnosing what actually went wrong. Both the builtin
        ExceptionGroup (py311+) and the `exceptiongroup` backport expose the
        real failures via `.exceptions`, so we recurse into that instead of
        relying on isinstance checks tied to a specific Python version.
        """
        sub_exceptions = getattr(e, "exceptions", None)
        if sub_exceptions:
            if _depth > 5:  # defensive: avoid runaway recursion on odd input
                return f"{type(e).__name__} (too deeply nested to unwrap further)"
            return " | ".join(
                GraphNodesMixin._describe_exception(sub, _depth + 1)
                for sub in sub_exceptions
            )

        description = f"{type(e).__name__}: {e}"
        cause = e.__cause__ or (e.__context__ if not e.__suppress_context__ else None)
        if cause is not None and cause is not e:
            description += (
                f" (caused by {GraphNodesMixin._describe_exception(cause, _depth + 1)})"
            )
        return description

    @staticmethod
    async def task(agent_name: str, task_description: str):
        """Launch an ephemeral subagent for a task."""
        CLIENTS: dict = subagents_registry.clients
        client = CLIENTS[agent_name]
        agent_extras = subagents_registry.extras[agent_name]

        try:
            async with client.session(agent_name) as session:
                tools: StructuredTool = await load_mcp_tools(session)
                agent = create_agent(
                    model=model_registry.subagent_llm.llm,
                    tools=tools,
                    response_format=ToolStrategy(AgentRetrievedResult),
                    system_prompt=agent_extras["prompt"],
                )

                # TODO The subagents should ONLY return the tool messages that are needed to answer the users questions. The tool messages should not be modified by the subagent.
                invoke_coro = agent.ainvoke(
                    {"messages": [{"role": "user", "content": task_description}]},
                    config={"recursion_limit": agent_extras["recursion_limit"]},
                )
                timeout_seconds = agent_extras.get("timeout_seconds")
                if timeout_seconds:
                    result = await asyncio.wait_for(
                        invoke_coro, timeout=timeout_seconds
                    )
                else:
                    result = await invoke_coro

                if not result["structured_response"].information_found:
                    return GraphNodesMixin._no_info_result(task_description)

                # e.g., ragflow mcp returns json string that need to be loaded into json
                # TODO consider just getting the result of the last tool call??
                tool_messages: list[dict] = [
                    msg.content[-1]
                    for msg in result["messages"]
                    if isinstance(msg, ToolMessage)
                ]

                if agent_extras["is_ragflow"]:
                    # NOTE: this assumes the ragflow chunk payload is the
                    # second-to-last tool message. Fragile if the subagent
                    # calls a different number/order of tools than expected
                    # (see bugs_to_fix.md #23) — guarded here just enough to
                    # avoid an IndexError, not to fully fix the assumption.
                    # The last tool message -1 is the structured output, message -2 is the actual tool message.
                    if len(tool_messages) < 2:
                        logger.error(
                            "[RAGFLOW] Expected at least 2 tool messages to extract "
                            f"chunk information, got {len(tool_messages)}"
                        )
                        return GraphNodesMixin._no_info_result(task_description)

                    text = tool_messages[-2].get("text", "")
                    if not text:
                        logger.error(
                            "[RAGFLOW] Chunk information could not be extracted"
                        )
                        return GraphNodesMixin._no_info_result(task_description)
                    chunks: dict = json.loads(text)

                    return GraphNodesMixin.extract_ragflow_chunks(
                        chunks=chunks["chunks"],
                        url_reference=agent_extras["reference_url"],
                        query=task_description,
                    )
                else:
                    combined_text = "\n\n".join(
                        msg.get("text", "")
                        for msg in tool_messages
                        if isinstance(msg, dict)
                    )
                    return RetrievalResult(
                        result_text=combined_text,
                        search_query=task_description,
                        retrieval_tool=RetrievalToolType.UNKNOWN,
                    )

        except Exception as e:
            log_event(
                "SUBAGENT_ERROR",
                "Subagent call failed; returning graceful fallback",
                level=logging.ERROR,
                agent_name=agent_name,
                task_description=task_description,
                error=GraphNodesMixin._describe_exception(e),
                # Full traceback too (truncated defensively) — the
                # unwrapped `error` field above names the real exception
                # type/message, but the traceback pinpoints exactly where
                # it happened, which matters for TaskGroup-wrapped MCP
                # session failures that don't otherwise say much.
                traceback=traceback.format_exc()[-4000:],
            )
            return GraphNodesMixin._no_info_result(task_description)

    @staticmethod
    def create_tools() -> List:
        """Create and configure tools for the chatbot's agent.

        Returns:
            List[BaseTool]: Configured tools for the agent
        """

        from src.chatbot.tools.search_web_tool import async_search

        # TODO: Tool descriptions are always in german (Translate to english)
        tools = [
            # StructuredTool.from_function(
            #     name=ToolNames.EXAMINATION_REGULATIONS_TOOL,
            #     coroutine=_examination_regulations_tool,
            #     description=translate_prompt()["examination_regulations"],
            #     args_schema=RetrieverInput,
            #     handle_tool_errors=True,
            # ),
            # TODO: Make serarch available through mcp
            StructuredTool.from_function(
                name=ToolNames.SEARCH_WEB_TOOL,
                coroutine=async_search,
                description=translate_prompt()["description_university_web_search"],
                args_schema=SearchInputWeb,
                handle_tool_errors=True,
            ),
        ]

        if settings.graph.troubleshooting.activate:
            tools.append(
                StructuredTool.from_function(
                    name=ToolNames.TROUBLESHOOTING_TOOL,
                    coroutine=_retriever_his_in_one_tool,
                    description=settings.graph.troubleshooting.description,
                    args_schema=HisInOneInput,
                    handle_tool_errors=True,
                )
            )
        # Check the populated registry (not just settings.mcp_agents), since
        # every configured agent could have enabled: False — Literal[()]
        # with zero options would otherwise raise when building the schema.
        if subagents_registry.agent_names:

            class _TaskInput(TaskInput):

                _TaskInput = create_model(
                    "TaskInput",
                    agent_name=(
                        Literal[tuple(subagents_registry.agent_names)],
                        Field(..., description="Agent name"),
                    ),
                    task_description=(str, Field(..., description="Task description")),
                    __base__=TaskInput,
                )

            tools.append(
                StructuredTool.from_function(
                    name=ToolNames.TASK,
                    coroutine=GraphNodesMixin.task,
                    description=subagents_registry.description,
                    args_schema=_TaskInput,
                    handle_tool_errors=True,
                )
            )

        return tools

    @staticmethod
    def filter_messages(messages: List[BaseMessage], k: int) -> List[BaseMessage]:
        """Filter messages to keep only the last k messages.
        During the run of the graph useless messages are gathered as byproduct of e.g., tool calls
        these messages are filtered out here to keep context clean.
        Args:
            messages: List of messages to filter
            k: Number of messages to keep

        Returns:
            List[BaseMessage]: Filtered messages
        """
        if len(messages) <= k:
            return messages

        return messages[-k:]

    async def agent_node(self, state: State) -> Dict:
        """Decide course of action.

        Args:
            state: Current state containing messages

        Returns:
            Dict: Updated state with agent response
        """
        # redis-langgraph short term memory feeds the chat history (ai-human) messages to the state[messages] automtically
        messages = state.get("messages", [])
        # Build the system message fresh every time from current state context
        current_date = state.get("current_date", "")
        user_initial_query = state.get("user_initial_query", "")
        language = state.get("language", "Deutsch")
        system_prompt = get_system_prompt(user_initial_query, current_date, language)

        # the list of messages grows with each graph iteration e.g., useless toolmessages etc. Here the list is shortened
        filtered_messages = self.filter_messages(messages, MESSAGE_HISTORY_LIMIT)

        # Prepend system message ONLY for the LLM call — never persisted to state
        # The first message in the conversation must be a SystemMessage.
        llm_messages = system_prompt + filtered_messages
        try:
            response = await self._llm_with_tools.ainvoke(llm_messages)
        except Exception as e:
            # node failure.
            logger.error(f"[LLM-OPERATION] LLM called failed: {e}")
            raise
        return {
            "messages": [_sanitize_ai_message(response)],
            "search_query": [],
        }

    async def judge_node(self, state: State) -> Dict:
        """Evaluate if agent's decision to not use tools was appropriate.

        Args:
            state: Current state

        Returns:
            Dict: Updated state with judgement result
        """
        language = state.get("language", "Deutsch")

        class JudgementResult(BaseModel):
            """Result of agent's tool usage judgement."""

            judgement_binary: Literal["yes", "no"] = Field(
                description="The agent must use a Tool 'yes', or 'no'"
            )
            reason: str = Field(
                description="Back up your decision with a short explanation"
            )

        llm_with_str_output = self._llm.with_structured_output(JudgementResult)
        prompt = PromptTemplate(
            template="""
               Your role is to evaluate whether an agent's choice not to utilize a tool was justifiable in a given interaction. 
            Tools are fundamental in ensuring responses are factual and free from errors (e.g., Hallucinations). 
            The agent must use the tools at its disposal to address user queries, rather than defaulting to its pre-trained knowledge. 
            **However**, there are specific scenarios where not using a tool is appropriate:

                1. When the agent needs to ask the user for more information or clarification.
                2. When the agent acknowledges or greets the user.
                3. When the agent informs the user that it can only respond to queries related to university matters.
                
                ### Evaluation Task:
                The agent has decided not to use a tool. Is the agent's decision correct?.  Provide a binary response of 'yes' or 'no':
                    - 'no': The agent incorrectly avoided using a tool and should have done so.
                    - 'yes': The agent's decision was appropriate, and utilizing a tool was unnecessary.
                
                Offer a rationale for your decision. Below, you will find the agent's message and the user's query:

                Agent (AI message):
                {context}

                User Query:
                {question}
            """,
            input_variables=["context", "question"],
        )

        chain = prompt | llm_with_str_output
        score = await chain.ainvoke(
            {"question": state["user_initial_query"], "context": state["messages"][-1]}
        )

        # Structured decision event: queryable later on decision/reason (e.g.
        # "how often does the agent skip tools when it shouldn't"), instead
        # of only being visible as free text when the decision was "no".
        log_event(
            "JUDGE_NODE",
            "Evaluated agent's decision to not use a tool",
            node="judge_node",
            decision=score.judgement_binary,
            reason=score.reason,
        )

        if score.judgement_binary.lower() == "no":
            # TODO use reducer to mange messages
            return {
                "messages": [
                    HumanMessage(
                        content=translate_internal_string("use_tool_msg", language)
                    )
                ],
                "score_judgement_binary": score.judgement_binary,
            }

        return {"score_judgement_binary": score.judgement_binary}

    async def tool_node(self, state: Dict) -> Dict:
        """Process tool calls."""

        from src.chatbot.tools.search_web_tool import async_search

        if messages := state.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")

        about_application = False
        teaching_degree = False
        tool_tasks = []  # gather later with asyncio

        # Read accumulated visited_links from State (not self)
        visited_links_so_far = state.get("visited_links", [])

        # TODO: FAQ support only available in RAGFLOW. Needs to be done with Milvus
        if settings.graph.faq.activate:
            if (
                state.get("rewrite_query", False)
                and settings.vector_db_settings.type
                == VectorDBTypes.INFINITY_RAGFLOW  # Infinity RAGFlow
            ):
                # message.tool_calls[0] isn't necessarily a query-style tool
                # call (e.g. the "task" tool used for MCP subagents has
                # agent_name/task_description args, not "query") -- only
                # attempt the FAQ shortcut when there's an actual query to
                # search with, otherwise retrieve_from_infinity_ragflow(...)
                # gets query=None and blows up building RetrievalResult
                # (search_query is a required str, not Optional).
                faq_query = message.tool_calls[0]["args"].get("query")
                if faq_query:
                    # if the agent is in the rewrite state, try to find answer in FAQs
                    tool_tasks.append(
                        retrieve_from_infinity_ragflow(
                            collection_name=settings.graph.faq.collection_name,
                            query=faq_query,
                            extract_reference_url=True,
                        )
                    )

        for tool_call in message.tool_calls:

            # TODO Write test for this
            if tool_call["name"] == ToolNames.SEARCH_WEB_TOOL:
                about_application = tool_call["args"].get("about_application", False)
                teaching_degree = tool_call["args"].get("teaching_degree", False)
                tool_call["args"]["do_not_visit_links"] = visited_links_so_far

                # TODO IF no results are found, the tool result is empty and the agent should generate a new query and search again
                # TODO even when no results are found, the entire graph executes e.g. grade_documents edge

                tool_tasks.append(async_search(**tool_call["args"]))

            # TODO: Unify all vector db based tools. They all should return the same format (text,(source, page))
            # elif tool_call["name"] == ToolNames.EXAMINATION_REGULATIONS_TOOL:

            #     tool_tasks.append(_examination_regulations_tool(**tool_call["args"]))

            elif (
                tool_call["name"] == ToolNames.TROUBLESHOOTING_TOOL
                and settings.graph.troubleshooting.activate
            ):

                tool_tasks.append(_retriever_his_in_one_tool(**tool_call["args"]))

            elif tool_call["name"] == ToolNames.TASK:
                tool_tasks.append(GraphNodesMixin.task(**tool_call["args"]))

        # Call tools
        retrieval_results: list[RetrievalResult] = await asyncio.gather(
            *tool_tasks, return_exceptions=True
        )

        outputs_txt, search_query, new_links, new_doc_refs = self._extract_tool_info(
            retrieval_results
        )
        # TODO Sometines the agent calls several tools and the tokens surpass the defined context window. Do summarization here.
        last_tool_usage = state["messages"][-1].additional_kwargs
        # Remove last ai message, otherwise it will be shown to the user (generated in agent node)
        last_msg = state["messages"][-1]
        return {
            "messages": [RemoveMessage(id=last_msg.id)],
            "tool_messages": outputs_txt,
            "last_tool_usage": last_tool_usage,  # last ai message with previous tool usage
            "search_query": search_query,
            "about_application": about_application,
            "teaching_degree": teaching_degree,
            "visited_links": new_links,
            "doc_references": new_doc_refs,
        }

    def rewrite(self, state):
        """
        Instruct the agent to rephrase the question.

        Args:
            state (messages): The current state

        Returns:
            dict: The updated state with re-phrased question
        """
        language = state.get("language", "Deutsch")
        user_query = state["user_initial_query"]

        # Structured event so rewrite frequency/patterns (e.g. "which queries
        # keep getting rewritten") can be analyzed later, not just observed
        # live in the moment.
        log_event(
            "REWRITE",
            "Instructing agent to rephrase the question",
            node="rewrite",
            original_query=user_query,
        )

        msg = [
            HumanMessage(
                content=translate_prompt(language)["rewrite_msg_human"].format(
                    user_query=user_query,
                    tool_history=state["last_tool_usage"],
                ),
            )
        ]
        last_msg = state["messages"][-1]
        return {
            "messages": [RemoveMessage(id=last_msg.id)] + msg,
            "rewrite_query": True,
        }

    async def generate_helper(self, state, system_message_generate):

        messages_history = state.get("messages", [])
        if not messages_history:
            logger.warning(
                "[LANGGRAPH] No message history found. Using system message only for generation."
            )
            _query_message = [HumanMessage(content=state.get("search_query", ""))]
            response = self._llm.invoke([system_message_generate] + _query_message)
            return {"messages": [_sanitize_ai_message(response)]}

        filtered_messages_history = self.filter_messages(
            messages_history, MESSAGE_HISTORY_LIMIT
        )
        message_deque = deque(filtered_messages_history)

        if isinstance(message_deque[0], SystemMessage):
            message_deque.popleft()
            message_deque.appendleft(system_message_generate)
        else:
            message_deque.appendleft(system_message_generate)

        # the last message should be the Human message.
        # At this point the last message is the ai message generated by the agent node
        if isinstance(message_deque[-1], AIMessage):
            message_deque.pop()

        first_msg = message_deque[0]
        if not isinstance(first_msg, SystemMessage):
            raise MustContainSystemMessageException(
                "The first message in the conversation must be a SystemMessage."
            )
        try:
            response: AIMessage = await self._llm.ainvoke(list(message_deque))
        except Exception as e:
            logger.error(f"[LLM-OPERATION] LLM called failed: {e}")
            raise

        logger.debug("[LANGGRAPH] Answer Generated... Sending to API...")

        return {
            "messages": [_sanitize_ai_message(response)],
        }

    async def generate(self, state: State) -> Dict:
        """Generate final answer based on retrieved documents.

        Args:
            state: Current state

        Returns:
            Dict: Updated state with generated response
        """
        logger.debug("[LANGGRAPH][GENERATE NODE] Generating answer")
        language = state.get("language", "Deutsch")
        tool_message = state.get("tool_messages", None)
        system_message_generate = SystemMessage(
            content=translate_prompt(language)["system_message_generate"].format(
                current_date=state.get("current_date", ""),
                user_query=state.get("search_query", ""),
                context=tool_message,
            )
        )
        return await self.generate_helper(state, system_message_generate)

    async def generate_application(self, state: State) -> Dict:

        logger.debug(["[LANGGRAPH][GENERATE APPLICATION NODE] Generating answer"])
        # tool_message = self._clean_tool_message or state.get("tool_messages", None)
        language = state.get("language", "Deutsch")
        tool_message = state.get("tool_messages", None)
        system_message_generate = SystemMessage(
            content=translate_prompt(language)[
                "system_message_generate_application"
            ].format(
                current_date=state.get("current_date", ""),
                user_query=state.get("search_query", ""),
                context=tool_message,
            )
        )
        return await self.generate_helper(state, system_message_generate)

    async def generate_teaching_degree_node(self, state: State) -> Dict:
        """Generate answer for teaching degree related queries.

        Args:
            state: Current state

        Returns:
            Dict: Updated state with generated response
        """
        language = state.get("language", "Deutsch")
        logger.debug("[LANGGRAPH][GENERATE TEACHING DEGREE NODE] Generating answer")
        tool_message = state.get("tool_messages", None)
        system_message_generate = SystemMessage(
            content=translate_prompt(language)[
                "system_message_generate_teaching_degree"
            ].format(
                current_date=state.get("current_date", ""),
                user_query=state.get("search_query", ""),
                context=tool_message,
            )
        )
        return await self.generate_helper(state, system_message_generate)


class GraphEdgesMixin:
    """Mixin class handling edge routing and decision making in the graph."""

    def route_tools(
        self,
        state: State,
    ) -> Literal["tool_node", "judge_node"]:
        """Route to tool_node if last message has tool calls, otherwise to judge_node.

        Args:
            state: Current state containing messages

        Returns:
            Literal["tool_node", "judge_node"]: Next node to route to

        Raises:
            ValueError: If no messages found in state
        """
        if isinstance(state, list):
            ai_message = state[-1]
        elif messages := state.get("messages", []):
            ai_message = messages[-1]
        else:
            raise ValueError(f"No messages found in input state to tool_edge: {state}")

        if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
            return "tool_node"
        return "judge_node"

    def route_end(self, state: State) -> Union[Literal["agent_node"], Literal[END]]:
        """Route to agent_node if hallucination check fails, otherwise to END.

        Args:
            state: Current state

        Returns:
            Union[Literal["agent_node"], Literal[END]]: Next node to route to
        """
        if state["pass_hallucinate_check"] == "no":
            return "agent_node"
        return END

    async def grade_documents(self, state: State) -> Literal["generate", "rewrite"]:
        """Evaluate if retrieved documents are relevant to the query.

        Args:
            state: Current state

        Returns:
            Literal["generate", "rewrite"]: Decision on document relevance
        """
        language = state.get("language", "Deutsch")
        tool_messages = state.get("tool_messages", "")
        if len(tool_messages) < 10:
            log_event(
                "GRADE_DOCUMENTS",
                "No tool messages found; routing to rewrite",
                node="grade_documents",
                decision="rewrite",
                reason="no_tool_messages",
            )
            return "rewrite"

        tool_query = " ".join(state["search_query"])

        class GradeResult(BaseModel):
            """Binary score for document relevance check."""

            binary_score: str = Field(
                description=translate_internal_string("grader_binary_score", language)
            )
            reason: str = Field(
                description="Back up your decision with a short explanation"
            )
            # relevant_paragraphs: Optional[str] = Field(
            #     description="From the retrieved documents, which paragraphs are relevant to answer the user query? Extract all relevant paragraphs from the retrieved documents."
            # )

        llm_with_str_output = self._llm.with_structured_output(GradeResult)
        prompt = PromptTemplate(
            template=translate_prompt(language)["grading_llm"],
            input_variables=["context", "question"],
        )
        chain = prompt | llm_with_str_output
        scored_result = await chain.ainvoke(
            {
                "question": f'{state["user_initial_query"]}, {tool_query}',
                "context": tool_messages,
            }
        )

        try:
            score = scored_result.binary_score.lower()
            if score in ["yes", "ja"]:
                # TODO Further process the relevant paragraphs
                # self._clean_tool_message = scored_result.relevant_paragraphs
                if state.get("teaching_degree", False):
                    next_node = "generate_teaching_degree_node"
                elif state.get("about_application", False):
                    next_node = "generate_application"
                else:
                    next_node = "generate"

                log_event(
                    "GRADE_DOCUMENTS",
                    "Documents graded relevant",
                    node="grade_documents",
                    decision=next_node,
                    reason=scored_result.reason,
                )
                return next_node

            else:
                log_event(
                    "GRADE_DOCUMENTS",
                    "Documents graded not relevant; routing to rewrite",
                    node="grade_documents",
                    decision="rewrite",
                    reason=scored_result.reason,
                )
                return "rewrite"
        except Exception as e:
            logger.error(
                f"[LANGGRAPH][GRADE DOCUMENTS EDGE] Error occurred while grading documents: {e}"
            )
            raise e

    def judge_agent_decision(
        self, state: State
    ) -> Union[Literal["agent_node"], Literal[END]]:
        """Judge if agent's decision to not use tools was appropriate.

        Args:
            state: Current state containing messages and judgement score

        Returns:
            Union[Literal["agent_node"], Literal[END]]: Next node based on judgement
        """
        score = state.get("score_judgement_binary", "")
        if score == "yes":
            # self._agent_direct_msg = state["messages"][-1].content[0]["text"]
            return END
        return "agent_node"
