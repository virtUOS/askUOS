import json
import uuid
from typing import Annotated, Any, ClassVar, Dict, List, Optional, Tuple

import streamlit as st
from langchain.tools.retriever import create_retriever_tool
from langchain_core.agents import AgentActionMessageLog, AgentFinish
from langchain_core.callbacks import (
    StdOutCallbackHandler,
    StreamingStdOutCallbackHandler,
)
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.pydantic_v1 import BaseModel, Field, PrivateAttr
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from typing_extensions import TypedDict

# from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from src.chatbot.db.vector_store import retriever
from src.chatbot.prompt.main import get_prompt
from src.chatbot.utils.agent_helpers import llm
from src.chatbot.utils.prompt import get_prompt_length, translate_prompt
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

OPEN_AI_MODEL = settings.model.model_name


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


class GraphEdgesMixin:
    def route_tools(
        self,
        state: State,
    ):
        """
        Use in the conditional_edge to route to the ToolNode if the last message
        has tool calls. Otherwise, route to the end.
        """
        if isinstance(state, list):
            ai_message = state[-1]
        elif messages := state.get("messages", []):
            ai_message = messages[-1]
        else:
            raise ValueError(f"No messages found in input state to tool_edge: {state}")
        if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
            return "tool_node"
        return END


class GraphNodesMixin:

    @staticmethod
    def create_tools() -> List[BaseTool]:
        """
        Creates a list of tools for the chatbot agent.

        Returns:
            List[BaseTool]: A list of tools for the chatbot agent.
        """
        from langchain.tools.base import StructuredTool

        from src.chatbot.tools.search_web_tool import search_uni_web

        return [
            create_retriever_tool(
                retriever,
                "technical_troubleshooting_questions",
                translate_prompt(settings.language)[
                    "description_technical_troubleshooting"
                ],
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
    def filter_messages(messages: List, k: int):
        if len(messages) <= k:
            return messages
        return messages[-k:]

    # Nodes
    def agent_node(self, state: State):
        # TODO if a tool was called, only pass the tool message, system message and human messageS
        messages = GraphNodesMixin.filter_messages(state["messages"], 5)
        # TODO pass callback to the llm_with_tools object, to detect when the tokens are generated and stream them
        # detect when AI message contains 'finish_reason':'stop' and start streaming the tokens
        reponse = self._llm_with_tools.invoke(messages)
        return {
            "messages": [reponse],
        }

    def tool_node(self, inputs: dict):
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")
        outputs = []
        for tool_call in message.tool_calls:
            tool_result = self._tools_by_name[tool_call["name"]].invoke(
                tool_call["args"]
            )
            outputs.append(
                ToolMessage(
                    content=json.dumps(tool_result),
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}

    def final_answer_node(self, state: State):
        # TODO create prompt for final answer generation. This LLM does not know about tools
        # TODO if a tool was called, only pass the tool message, system message and human messages
        # TODO Assess the effect of exlcluding AI messages from the input
        prompt = get_prompt(state["messages"], "system_message")
        last_ai_message = state["messages"][-1]
        response = self._llm.invoke(prompt)
        response.id = last_ai_message.id
        return {"messages": [response]}


class CampusManagementOpenAIToolsAgent(BaseModel, GraphNodesMixin, GraphEdgesMixin):

    # Singleton instance
    _instance: ClassVar[Optional["CampusManagementOpenAIToolsAgent"]] = None

    _tools_by_name: List[BaseTool] = PrivateAttr(default=None)

    # TODO have a global llm object, that can be used throgout the application
    _llm: ChatOpenAI = PrivateAttr(default=None)
    # important: the code uses function calling as opposed to tool calling. (DEPENDS ON THE MODEL and how it was fine tuned)
    _llm_with_tools: ChatOpenAI = PrivateAttr(default=None)
    language: str = Field(default=settings.language)
    # TODO shold not be a private attribute
    _graph: StateGraph = PrivateAttr(default=None)

    # (not part of the model schema)
    _chat_history: List[Dict] = PrivateAttr(default=[])
    _prompt_length: int = PrivateAttr(default=None)

    def __new__(cls, *args, **kwargs):

        if cls._instance is None:
            cls._instance = super(CampusManagementOpenAIToolsAgent, cls).__new__(cls)
            logger.debug("Creating a new instance of CampusManagementOpenAIToolsAgent")

        # create a new instance if the language changes
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

        # graph_builder.add_node("final_answer_node", self.final_answer_node)

        graph_builder.add_edge(START, "agent_node")

        graph_builder.add_edge("tool_node", "agent_node")

        graph_builder.add_conditional_edges(
            "agent_node",
            self.route_tools,
            {
                "tool_node": "tool_node",
                END: END,
            },  # if route_tools returns "tool_node", the graph will route to the "tool_node" node, else it will route to the END node
        )

        # Memory is currently handled using streamlit session state
        # memory = MemorySaver()
        self._graph = graph_builder.compile()

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
            + self.llm.get_num_tokens(query)
        )
        return internal_tokens

    def __call__(self, input: str):

        # TODO delete this __call__ method (or reuse stream_graph_updates fuction in ask_uos_chat.py) )
        # TODO another option: adapt the method for debugging purposes: stream using print instead of streamlit
        final_answer = ""
        content_stream = ""
        thread_id = uuid.uuid4()
        config = {
            "configurable": {"thread_id": thread_id},
        }
        prompt = get_prompt([("user", input)])
        try:

            for msg_chunk, metadata in self._graph.stream(
                {"messages": prompt},
                config=config,
                stream_mode="messages",
            ):
                if (
                    msg_chunk.content
                    and not isinstance(msg_chunk, HumanMessage)
                    and metadata["langgraph_node"] == "final_answer_node"
                ):
                    final_answer = final_answer + msg_chunk.content
                    # stream per line
                    if "\n" in msg_chunk:
                        content_stream += msg_chunk
                        st.markdown(content_stream)
                        self.content = ""
                    else:
                        content_stream += msg_chunk
            # if there is content left, stream it
            if content_stream:
                st.markdown(content_stream)
            return final_answer

        except Exception as e:
            logger.error(f"An error occurred while generating reponse: {e}")

            return {
                "output": "An error has occurred while trying to connect to the data source or APIs. Please try asking the question again."
            }

    @classmethod
    def run(cls, *args, **kwargs):

        instance = cls(*args, **kwargs)
        return instance


if __name__ == "__main__":

    graph = CampusManagementOpenAIToolsAgent.run()

    def print_graph(graph, filename="graph.png"):
        from IPython.display import Image, display

        try:
            # Generate the PNG from the graph
            png_data = graph.get_graph().draw_mermaid_png()

            # Save the PNG data to a file
            with open(filename, "wb") as f:
                f.write(png_data)

            # Display the image
            display(Image(filename))
        except Exception as e:
            print(f"An error occurred: {e}")
            # Optional: handle any additional logic or fallback

    print_graph(graph._graph)

    response = graph("Tell me about the biology program?")

    thread_id = uuid.uuid4()
    config = {
        "configurable": {"thread_id": thread_id},
    }

    user_input = "Tell me about the biology program?"

    def stream_graph_updates(user_input):
        final_answer = ""
        prompt = get_prompt([("user", user_input)])
        # msg_chunk: token streamed by the llm
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

    # stream_graph_updates("yes i want to sign for the bachelors")
    stream_graph_updates("Tell me about the computer science program at the uni?")
    # stream_graph_updates("what are the requirements?")
    print("Done")
