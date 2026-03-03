
import asyncio
from collections import deque
from typing import ClassVar, Dict, List, Literal, Optional, Union

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import PromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from src.chatbot.agents.models import Reference, RetrievalResult
from src.chatbot.agents.utils.agent_retriever import (
    _examination_regulations_tool,
    _retriever_his_in_one_tool,
    retrieve_from_infinity_ragflow,
)
from src.chatbot.prompt.main import (
    translate_prompt,
)

from langchain.messages import RemoveMessage
from src.chatbot.tools.utils.tool_helpers import ReferenceRetriever
from src.chatbot.tools.utils.tool_schema import (
    HisInOneInput,
    RetrieverInput,
    SearchInputWeb,
)
from src.chatbot.prompt.main import get_system_prompt
from langgraph.graph.message import add_messages
from src.chatbot.utils.constants import ToolNames
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings
from src.config.models import CollectionNames, VectorDBTypes
from typing_extensions import TypedDict
from langgraph.runtime import Runtime 
from typing import Annotated
from src.chatbot.agents.utils.exceptions import MustContainSystemMessageException
from langgraph.graph.message import RemoveMessage
# Importat when it comes to models with restricted context window
MESSAGE_HISTORY_LIMIT = 7

# TODO Verify if this step is necessary
def _sanitize_ai_message(message: AIMessage) -> AIMessage:
    """Strip non-serializable metadata."""
    return AIMessage(
        content=message.content,
        tool_calls=message.tool_calls or [],
        additional_kwargs= message.additional_kwargs or {},
        id=message.id,
    )

def add_lists(existing: list, new: list) -> list:
    """Reducer that accumulates list items across nodes."""
    return existing + new

class State(TypedDict):
    """State management for the graph-based agent.

    Attributes:

        messages: List of messages in the conversation
        search_query: Optional list of queries used for web/db searches
        user_initial_query: Optional string containing the user's initial query
        answer_rejection: Optional string for rejected answers
        score_judgement_binary: Optional string for binary judgement scores
    """

    messages: Annotated[list[BaseMessage], add_messages]
    search_query: Optional[List[str]]
    user_initial_query: Optional[str]
    current_date: Optional[str] 
    answer_rejection: Optional[str]
    score_judgement_binary: Optional[str]
    about_application: Optional[bool] # To determine which node generates the answer (!!!set to False when invoking graph)
    teaching_degree: Optional[bool] # To determine which node generates the answer  (!!!set to False when invoking graph)
    tool_messages: Optional[str]
    last_tool_usage: Optional[dict]
    rewrite_query: bool  # Flag to indicate if the query should be rewritten (!!!set to False when invoking graph)
    # ---- Per-request references----
    visited_links: Annotated[list[str], add_lists]
    doc_references: Annotated[list, add_lists]  # list of doc reference objects
    language: Optional[str]  #Literal["Deutsch", "English"]

class GraphNodesMixin:
    """Mixin class handling node operations in the graph."""

    def _extract_tool_info(self, retrieval_result: List[RetrievalResult]):
        outputs_txt = ""
        search_query = []
        new_links = []
        new_doc_refs = []

        for result in retrieval_result:
            if isinstance(result, Exception):
                logger.error(f"Tool call failed: {result}")
                continue
            if result.source_name == CollectionNames.FAQ:
                unique_refs = {item.url_reference_askuos for item in result.reference}
                new_links.extend(unique_refs)
            elif result.source_name in (
                CollectionNames.EXAMINATION_REGULATIONS,
                CollectionNames.TROUBLESHOOTING,
            ):
                new_doc_refs.extend(result.reference)

            # web search
            else:
                new_links.extend(result.reference)

            outputs_txt += result.result_text + "\n\n"
            search_query.append(result.search_query)

        return outputs_txt, search_query, new_links, new_doc_refs

    @staticmethod
    def create_tools() -> List:
        """Create and configure tools for the chatbot's agent.

        Returns:
            List[BaseTool]: Configured tools for the agent
        """
        from langchain_classic.tools import StructuredTool
        from src.chatbot.tools.search_web_tool import async_search
        # TODO: Tool descriptions are always in german (Translate to english)
        return [
            StructuredTool.from_function(
                name=ToolNames.TROUBLESHOOTING_TOOL,
                coroutine=_retriever_his_in_one_tool,
                description=translate_prompt()["HISinOne_troubleshooting_questions"],
                args_schema=HisInOneInput,
                handle_tool_errors=True,
            ),
            StructuredTool.from_function(
                name=ToolNames.EXAMINATION_REGULATIONS_TOOL,
                coroutine=_examination_regulations_tool,
                description=translate_prompt()["examination_regulations"],
                args_schema=RetrieverInput,
                handle_tool_errors=True,
            ),
            StructuredTool.from_function(
                name=ToolNames.SEARCH_WEB_TOOL,
                coroutine=async_search,
                description=translate_prompt()["description_university_web_search"],
                args_schema=SearchInputWeb,
                handle_tool_errors=True,
            ),
        ]

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

    def agent_node(self, state: State) -> Dict:
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
        response = self._llm_with_tools.invoke(llm_messages)
        return {
            "messages": [_sanitize_ai_message(response)],
            "search_query": [],
        }

    def judge_node(self, state: State) -> Dict:
        """Evaluate if agent's decision to not use tools was appropriate.

        Args:
            state: Current state

        Returns:
            Dict: Updated state with judgement result
        """
        language = state.get("language", "Deutsch")
        logger.debug("[LANGGRAPH][JUDGE NODE] Evaluating agent's decision to use tools")

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
        score = chain.invoke(
            {"question": state["user_initial_query"], "context": state["messages"][-1]}
        )

        if score.judgement_binary.lower() == "no":
            logger.debug(
                f"[LANGGRAPH][JUGE NODE] The agent should have used a tool. Reason: {score.reason}"
            )
            # TODO use reducer to mange messages
            return {
                "messages": [HumanMessage(content=translate_prompt(language)["use_tool_msg"])],
                "score_judgement_binary": score.judgement_binary,
            }

        return {"score_judgement_binary": score.judgement_binary}

    async def tool_node(self, state: Dict) -> Dict:
        """Process tool calls. """

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
        if (
            state.get("rewrite_query", False)
            and settings.vector_db_settings.type
            == VectorDBTypes.INFINITY_RAGFLOW  # Infinity RAGFlow
        ):
            # if the agent is in the rewrite state, try to find answer in FAQs
            tool_tasks.append(
                retrieve_from_infinity_ragflow(
                    collection_name=CollectionNames.FAQ.value,
                    query=message.tool_calls[0]["args"].get("query"),
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
            elif tool_call["name"] == ToolNames.EXAMINATION_REGULATIONS_TOOL:

                tool_tasks.append(_examination_regulations_tool(**tool_call["args"]))

            elif tool_call["name"] == ToolNames.TROUBLESHOOTING_TOOL:

                tool_tasks.append(_retriever_his_in_one_tool(**tool_call["args"]))

        # Call tools
        retrieval_results: RetrievalResult = await asyncio.gather(
            *tool_tasks, return_exceptions=True
        )
        outputs_txt, search_query, new_links, new_doc_refs = self._extract_tool_info(retrieval_results)
        # TODO Sometines the agent calls several tools and the tokens surpass the defined context window. Do summarization here.

        last_tool_usage = state["messages"][-1].additional_kwargs
        # Remove last ai message (generated in agent node)
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

        msg = [
            HumanMessage(
                content=translate_prompt(language)["rewrite_msg_human"].format(
                    user_query,
                    state["last_tool_usage"],
                )
            )
        ]
        last_msg = state["messages"][-1]
        return {"messages": [RemoveMessage(id=last_msg.id)] + msg, 
                "rewrite_query": True}

    def generate_helper(self, state, system_message_generate):
       
        messages_history = state.get("messages", [])
        if not messages_history:
            logger.warning("[LANGGRAPH] No message history found. Using system message only for generation.")
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
        response:AIMessage = self._llm.invoke(list(message_deque))
        
        return {
            "messages": [_sanitize_ai_message(response)],
            }

    def generate(self, state: State) -> Dict:
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
                state.get("current_date", ""),
                state.get("search_query", ""),
                tool_message,
            )
        )
        return self.generate_helper(state, system_message_generate)

    def generate_application(self, state: State) -> Dict:

        logger.debug(["[LANGGRAPH][GENERATE APPLICATION NODE] Generating answer"])
        # tool_message = self._clean_tool_message or state.get("tool_messages", None)
        language = state.get("language", "Deutsch")
        tool_message = state.get("tool_messages", None)
        system_message_generate = SystemMessage(
            content=translate_prompt(language)["system_message_generate_application"].format(
                state.get("current_date", ""),
                state.get("search_query", ""),
                tool_message,
            )
        )
        return self.generate_helper(state, system_message_generate)

    def generate_teaching_degree_node(self, state: State) -> Dict:
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
                state.get("current_date", ""),
                state.get("search_query", ""),
                tool_message,
            )
        )
        return self.generate_helper(state, system_message_generate)


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

    def grade_documents(self, state: State) -> Literal["generate", "rewrite"]:
        """Evaluate if retrieved documents are relevant to the query.

        Args:
            state: Current state

        Returns:
            Literal["generate", "rewrite"]: Decision on document relevance
        """
        language = state.get("language", "Deutsch")
        tool_messages = state.get("tool_messages", "")
        if len(tool_messages) < 10:
            logger.debug("[LANGGRAPH] GRADE DOCUMENTS EDGE: No tool messages found")
            return "rewrite"

        tool_query = " ".join(state["search_query"])

        class GradeResult(BaseModel):
            """Binary score for document relevance check."""

            binary_score: str = Field(
                description=translate_prompt(language)["grader_binary_score"]
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
        scored_result = chain.invoke(
            {
                "question": f'{state["user_initial_query"]}, {tool_query}',
                "context": tool_messages,
            }
        )

        try:
            # score = scored_result.binary_score.lower()
            score = scored_result.binary_score.lower()
            if score.lower() in ["yes", "ja"]:
                # TODO Further process the relevant paragraphs
                # self._clean_tool_message = scored_result.relevant_paragraphs
                logger.debug(
                    f"[LANGGRAPH][GRADE DOCUMENTS EDGE] DECISION: DOCS RELEVANT. Reason: {scored_result.reason}"
                )
                if state.get("teaching_degree", False):
                    return "generate_teaching_degree_node"

                elif state.get("about_application", False):
                    return "generate_application"
                else:
                    return "generate"

            else:
                logger.debug(
                    f"[LANGGRAPH][GRADE DOCUMENTS EDGE] DECISION: DOCS NOT RELEVANT. Reason: {scored_result.reason}"
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
            #self._agent_direct_msg = state["messages"][-1].content[0]["text"]
            return END
        return "agent_node"
