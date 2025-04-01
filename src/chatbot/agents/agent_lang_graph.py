import json
import uuid
from collections import deque
from typing import Annotated, ClassVar, Dict, List, Literal, Optional, Union

import streamlit as st
from langchain.tools.retriever import create_retriever_tool
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field, PrivateAttr
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from src.chatbot.db.clients import get_retriever
from src.chatbot.prompt.main import get_system_prompt
from src.chatbot.tools.utils.tool_helpers import visited_docs
from src.chatbot.utils.agent_helpers import llm
from src.chatbot.utils.agent_retriever import RetrieverInput, _get_relevant_documents
from src.chatbot.utils.prompt import get_prompt_length, translate_prompt
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

OPEN_AI_MODEL = settings.model.model_name
DEBUG = settings.application.debug


class State(TypedDict):
    """State management for the graph-based agent.

    Attributes:
        messages: List of messages in the conversation, with add_messages annotation for proper state updates
        search_query: Optional list of queries used for web/db searches
        user_initial_query: Optional string containing the user's initial query
        answer_rejection: Optional string for rejected answers
        score_judgement_binary: Optional string for binary judgement scores
    """

    messages: Annotated[List[BaseMessage], add_messages]
    search_query: Optional[List[str]]
    user_initial_query: Optional[str]
    current_date: Optional[str]
    answer_rejection: Optional[str]
    score_judgement_binary: Optional[str]


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
        messages = state["messages"]
        tool_messages = [i for i in messages if isinstance(i, ToolMessage)]
        tool_message = tool_messages[-1] if tool_messages else None
        tool_query = " ".join(state["search_query"])

        class GradeResult(BaseModel):
            """Binary score for document relevance check."""

            binary_score: str = Field(
                description=translate_prompt(settings.language)["grader_binary_score"]
            )

        llm_with_str_output = self._llm.with_structured_output(GradeResult)
        prompt = PromptTemplate(
            template=translate_prompt(settings.language)["grading_llm"],
            input_variables=["context", "question"],
        )
        chain = prompt | llm_with_str_output
        scored_result = chain.invoke(
            {"question": tool_query, "context": tool_message.content}
        )

        score = scored_result.binary_score.lower()
        if score in ["yes", "ja"]:
            logger.debug("---DECISION: DOCS RELEVANT---")
            return "generate"
        else:
            logger.debug("---DECISION: DOCS NOT RELEVANT---")
            return "rewrite"

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
            self._agent_direct_msg = state["messages"][-1].content
            return END
        return "agent_node"


class GraphNodesMixin:
    """Mixin class handling node operations in the graph."""

    @staticmethod
    def create_tools() -> List[BaseTool]:
        """Create and configure tools for the chatbot agent.

        Returns:
            List[BaseTool]: Configured tools for the agent
        """
        from langchain.tools.base import StructuredTool

        from src.chatbot.tools.search_web_tool import search_uni_web

        return [
            create_retriever_tool(
                retriever=get_retriever(
                    "troubleshooting"
                ),  # TODO make this configurable
                name="HISinOne_troubleshooting_questions",
                description=translate_prompt(settings.language)[
                    "HISinOne_troubleshooting_questions"
                ],
            ),
            StructuredTool.from_function(
                name="examination_regulations",
                func=_get_relevant_documents,
                description=translate_prompt(settings.language)[
                    "examination_regulations"
                ],
                args_schema=RetrieverInput,
                handle_tool_errors=True,
            ),
            StructuredTool.from_function(
                name="custom_university_web_search",
                func=search_uni_web.run,
                description=translate_prompt(settings.language)[
                    "description_university_web_search"
                ],
                handle_tool_errors=True,
            ),
        ]

    @staticmethod
    def filter_messages(messages: List[BaseMessage], k: int) -> List[BaseMessage]:
        """Filter messages to keep only the last k messages.

        Args:
            messages: List of messages to filter
            k: Number of messages to keep

        Returns:
            List[BaseMessage]: Filtered messages
        """
        # TODO make sure that the system message is always kept
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
        messages = self.filter_messages(state["messages"], 7)
        response = self._llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "search_query": [],
        }

    def judge_node(self, state: State) -> Dict:
        """Evaluate if agent's decision to not use tools was appropriate.

        Args:
            state: Current state

        Returns:
            Dict: Updated state with judgement result
        """

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
            msg = [
                HumanMessage(
                    content=translate_prompt(settings.language)["use_tool_msg"]
                )
            ]
            return {"messages": msg, "score_judgement_binary": score.judgement_binary}

        return {"score_judgement_binary": score.judgement_binary}

    def tool_node(self, inputs: Dict) -> Dict:
        """Process tool calls.

        Args:
            inputs: Dictionary containing messages

        Returns:
            Dict: Updated state with tool responses

        Raises:
            ValueError: If no messages found in input
        """
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")

        outputs = []
        search_query = []
        visited_docs.clear()

        for tool_call in message.tool_calls:
            try:
                tool_result = self._tools_by_name[tool_call["name"]].invoke(
                    tool_call["args"]
                )
            except Exception as e:
                logger.error(f"Error invoking tool: {e}")
                raise e

            tool_m = ToolMessage(
                content=json.dumps(tool_result),
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )

            # TODO tool message is a dictionary, needs further processing
            # TODO add the retrieved documents name and page to the visited links object
            outputs.append(tool_m)
            search_query.append(tool_call["args"].get("query", ""))

        # TODO Sometines the agent calls several tools and the tokens surpass the defined context window. Do summarization here.
        return {"messages": outputs, "search_query": search_query}

    def rewrite(self, state):
        """
        Instruct the agent to rephrase the question.

        Args:
            state (messages): The current state

        Returns:
            dict: The updated state with re-phrased question
        """

        user_query = state["user_initial_query"]

        # TODO delete previous tool messages as they do not inform the users query

        state["messages"] = [
            i for i in state["messages"] if not isinstance(i, ToolMessage)
        ]

        msg = [
            HumanMessage(
                content=translate_prompt(settings.language)["rewrite_msg_human"].format(
                    user_query,
                )
            )
        ]

        return {"messages": msg}

    def generate(self, state: State) -> Dict:
        """Generate final answer based on retrieved documents.

        Args:
            state: Current state

        Returns:
            Dict: Updated state with generated response
        """
        logger.debug("---GENERATE---")

        messages = state.get("messages", [])
        if not messages:
            logger.error("No messages found in state")
            return {"messages": []}

        # TODO inject the original user query and tool message as context in the generation system message

        message_deque = deque(messages)

        # shorter system prompt that does not include the tools description
        generate_message = SystemMessage(
            content=translate_prompt(settings.language)[
                "system_message_generate"
            ].format(
                state["current_date"],
                state["user_initial_query"],
            )
        )

        if isinstance(message_deque[0], SystemMessage):
            message_deque.popleft()
            message_deque.appendleft(generate_message)
        else:
            message_deque.appendleft(generate_message)

        response = self._llm.invoke(list(message_deque))
        return {"messages": [response]}


class CampusManagementOpenAIToolsAgent(BaseModel, GraphNodesMixin, GraphEdgesMixin):

    # Singleton instance
    _instance: ClassVar[Optional["CampusManagementOpenAIToolsAgent"]] = None

    _tools_by_name: List[BaseTool] = PrivateAttr(default=None)

    # TODO have a global llm object, that can be used throgout the application
    _llm: ChatOpenAI = PrivateAttr(default=None)
    # important: the code uses function calling as opposed to tool calling. (DEPENDS ON THE MODEL and how it was fine tuned)
    _llm_with_tools: ChatOpenAI = PrivateAttr(default=None)
    # _llm_answer_grader: ChatOpenAI = PrivateAttr(default=None)
    language: str = Field(default=settings.language)
    # TODO should not be a private attribute
    _graph: StateGraph = PrivateAttr(default=None)
    _chat_history: List[Dict] = PrivateAttr(default=[])
    _prompt_length: int = PrivateAttr(default=None)
    _agent_direct_msg: str = PrivateAttr(default=None)

    def __new__(cls, *args, **kwargs):
        """Create or retrieve singleton instance.

        Creates a new instance if none exists or if language changes.
        """
        if cls._instance is None:
            cls._instance = super(CampusManagementOpenAIToolsAgent, cls).__new__(cls)
            logger.debug("Creating a new instance of CampusManagementOpenAIToolsAgent")

        elif hasattr(
            cls._instance, "language"
        ) and cls._instance.language != kwargs.get("language", settings.language):
            # TODO preserve the memory of the previous agent (when the language changes and a previous conversation is still ongoing)
            # TODO provicional solution: chat history is being kept in the session state
            cls._instance = super(CampusManagementOpenAIToolsAgent, cls).__new__(cls)
            logger.debug(
                "Language changed: creating a new instance of CampusManagementOpenAIToolsAgent"
            )

        return cls._instance

    def __init__(self, **data):
        # data: key-value pairs passed through the run method, e.g., CampusManagementOpenAIToolsAgent.run(language='Deutsch')
        if not self.__dict__:
            super().__init__(**data)
            logger.debug(f"Language set to: {self.language}")

            self._llm = llm()

            tools = GraphNodesMixin.create_tools()
            self._tools_by_name = {tool.name: tool for tool in tools}
            # important: the code uses function calling as opposed to tool calling. (DEPENDS ON THE MODEL and how it was fine tuned)
            self._llm_with_tools = self._llm.bind_tools(tools)
            self._prompt_length = get_prompt_length(self.language)
            self._create_graph()

    def _create_graph(self):
        graph_builder = StateGraph(State)

        graph_builder.add_node("agent_node", self.agent_node)

        graph_builder.add_node("tool_node", self.tool_node)
        graph_builder.add_node("judge_node", self.judge_node)
        graph_builder.add_node("rewrite", self.rewrite)  # Re-writing the question
        graph_builder.add_node(
            "generate", self.generate
        )  # Generating a response after we know the documents are relevant
        # Call agent node to decide to retrieve or not
        graph_builder.add_edge(START, "agent_node")

        graph_builder.add_conditional_edges(
            "judge_node",
            self.judge_agent_decision,
            {"agent_node": "agent_node", END: END},
        )

        # Decide whether to retrieve
        graph_builder.add_conditional_edges(
            "agent_node",
            # Assess agent decision
            self.route_tools,
            {
                # Translate the condition outputs to nodes in our graph
                "tool_node": "tool_node",
                "judge_node": "judge_node",
            },
        )

        # Edges taken after the `action` node is called.
        graph_builder.add_conditional_edges(
            "tool_node",
            # Assess agent decision
            self.grade_documents,
        )
        graph_builder.add_edge("generate", END)
        graph_builder.add_edge("rewrite", "agent_node")

        self._graph = graph_builder.compile(debug=DEBUG)

    def compute_search_num_tokens(self, search_result_text: str) -> int:

        search_result_text_tokens = self._llm.get_num_tokens(search_result_text)

        return search_result_text_tokens

    def compute_internal_tokens(self, query: str) -> int:
        # extract the chat history from the memory
        # TODO BUG: Agent's scratchpad tokens are not being counted (fix sum(count_tokens_history) * 2)
        # history = self._agent_executor.memory.dict()["chat_memory"][
        #     "messages"
        # ]  # this is a list [{'content':'', 'additional_kwargs':{},...}, {}...]
        # history = self._get_chat_history()

        count_tokens_history = [
            self._llm.get_num_tokens(c["content"]) for c in self._chat_history
        ]
        # TODO multiply by 2 to account for agent's scratchpad (Improvement: use tokenization algorithm to count tokens)
        internal_tokens = (
            sum(count_tokens_history) * 2
            + self._prompt_length
            + self._llm.get_num_tokens(query)
        )
        return internal_tokens

    def __call__(self, input: str) -> Union[str, Dict]:
        """Process user input and generate response.

        Args:
            input: User input text

        Returns:
            Union[str, Dict]: Generated response or error message
        """

        thread_id = uuid.uuid4()
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.application.recursion_limit,
        }
        prompt = get_system_prompt([("user", input)])

        try:
            response = self._graph.invoke(
                {
                    "messages": prompt,
                    "user_initial_query": input,
                },
                config=config,
            )

            # returns last message content which is the AI message
            return response["messages"][-1].content

        except Exception as e:
            logger.error(f"An error occurred while generating response: {e}")
            return {
                "output": "An error has occurred while trying to connect to the data source or APIs. Please try asking the question again."
            }

    @classmethod
    def run(cls, *args, **kwargs) -> "CampusManagementOpenAIToolsAgent":
        """Create and return an instance of the agent.

        Returns:
            CampusManagementOpenAIToolsAgent: Configured agent instance
        """
        instance = cls(*args, **kwargs)
        return instance


if __name__ == "__main__":
    from src.chatbot.prompt.main import get_system_prompt

    graph = CampusManagementOpenAIToolsAgent.run()

    def print_graph(graph, filename="graph.png"):
        """Print the conversation graph as a PNG image.

        Args:
            graph: Graph to visualize
            filename: Output filename
        """
        from IPython.display import Image, display

        try:
            png_data = graph.get_graph().draw_mermaid_png()
            with open(filename, "wb") as f:
                f.write(png_data)
            display(Image(filename))
        except Exception as e:
            print(f"An error occurred: {e}")

    print_graph(graph._graph)

    thread_id = uuid.uuid4()
    config = {
        "configurable": {"thread_id": thread_id},
    }

    user_input = "How can i change the password of my stud.ip account?"
    prompt = get_system_prompt([("user", user_input)])
    response = graph._graph.invoke({"messages": prompt}, config=config)

    def stream_graph_updates(user_input: str) -> str:
        """Stream updates from graph processing.

        Args:
            user_input: User query to process

        Returns:
            str: Final response
        """
        final_answer = ""
        prompt = get_system_prompt([("user", user_input)])
        for msg_chunk, metadata in graph.stream(
            {"messages": prompt},
            config=config,
            stream_mode="messages",
        ):
            if (
                msg_chunk.content
                and not isinstance(msg_chunk, HumanMessage)
                and metadata["langgraph_node"] == "final_answer"
            ):
                final_answer = final_answer + msg_chunk.content
                print(msg_chunk.content, end="|", flush=True)
        return final_answer

    response = stream_graph_updates(user_input)
    stream_graph_updates("Tell me about the computer science program at the uni?")
    print("Done")


# "As a grader, your task is to evaluate whether an LLM generated answer effectively addresses and resolves a user's query while being based on the retrieved information. Assign a binary score:
# 'yes' if the answer fulfills both criteria (it resolves the user query
# and is grounded in the retrieved information) or 'no' if it fails to meet either or both criteria."
