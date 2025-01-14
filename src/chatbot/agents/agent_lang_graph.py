import json
from json import JSONDecodeError
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Annotated
from typing_extensions import TypedDict
import time
import streamlit as st
from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain.memory.utils import get_prompt_input_key
from langchain.tools.retriever import create_retriever_tool
from langchain_core.agents import AgentActionMessageLog, AgentFinish
from langchain_core.callbacks import (
    StdOutCallbackHandler,
    StreamingStdOutCallbackHandler,
)
from langchain_core.exceptions import OutputParserException
from langchain_core.memory import BaseMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field, PrivateAttr
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from src.chatbot.db.vector_store import retriever
from src.config.core_config import settings
from src.chatbot.utils.prompt import translate_prompt, get_prompt_length
from src.chatbot.prompt.main import get_prompt
from src.chatbot_log.chatbot_logger import logger
from src.chatbot.utils.agent_helpers import llm
from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from langchain_core.messages import ToolMessage
import uuid


OPEN_AI_MODEL = settings.model.model_name

agent_executor = CampusManagementOpenAIToolsAgent.run()

llm = ChatOpenAI(
    model=OPEN_AI_MODEL,
    temperature=0,
)


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


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
            translate_prompt()["description_technical_troubleshooting"],
        ),
        StructuredTool.from_function(
            name="custom_university_web_search",
            func=search_uni_web.run,
            description=translate_prompt()["description_university_web_search"],
            handle_tool_errors=True,
        ),
    ]


tools = create_tools()

# important: the code uses function calling as opposed to tool calling. (DEPENDS ON THE MODEL and how it was fine tuned)
llm_with_tools = llm.bind_tools(tools)

memory = MemorySaver()


def filter_messages(messages: List, k: int):
    if len(messages) <= k:
        return messages
    return messages[-k:]


# nodes


class ToolNode:
    """A node that runs the tools requested in the last AIMessage."""

    def __init__(self, tools: list) -> None:
        self.tools_by_name = {tool.name: tool for tool in tools}

    def __call__(self, inputs: dict):
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")
        outputs = []
        for tool_call in message.tool_calls:
            tool_result = self.tools_by_name[tool_call["name"]].invoke(
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


def final_answer(state: State):
    # TODO create prompt for final answer generation. This LLM does not know about tools
    last_ai_message = state["messages"][-1]
    response = llm.invoke(state["messages"])
    response.id = last_ai_message.id
    return {"messages": [response]}


def chatbot(state: State):
    # TODO if a tool was called, only pass the tool message, system message and human messageS
    messages = filter_messages(state["messages"], 5)
    return {"messages": [llm_with_tools.invoke(messages)]}


# Edges


def route_tools(
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
        return "tools"
    return "final_answer"


tool_node = ToolNode(tools=tools)

graph_builder = StateGraph(State)

graph_builder.add_node("chatbot", chatbot)

graph_builder.add_node("tools", tool_node)

graph_builder.add_node("final_answer", final_answer)

graph_builder.add_edge(START, "chatbot")

graph_builder.add_conditional_edges(
    "chatbot",
    route_tools,
    {
        "tools": "tools",
        "final_answer": "final_answer",
    },  # if route_tools returns "tools", the graph will route to the "tools" node, else it will route to the END node
)

graph_builder.add_edge("final_answer", END)


graph = graph_builder.compile(checkpointer=memory)


if __name__ == "__main__":
    thread_id = uuid.uuid4()
    config = {"configurable": {"thread_id": thread_id}}

    user_input = "who are you?"

    def stream_graph_updates(user_input):
        final_answer = ""
        prompt = get_prompt([("user", user_input)])
        for msg, metadata in graph.stream(
            {"messages": prompt}, stream_mode="messages", config=config
        ):
            if (
                msg.content
                and not isinstance(msg, HumanMessage)
                and metadata["langgraph_node"] == "final_answer"
            ):
                final_answer = final_answer + msg.content
                print(msg.content, end="|", flush=True)
        return final_answer

    response = stream_graph_updates(user_input)

    stream_graph_updates("yes i want to sign for the bachelors")
    stream_graph_updates("how much does it cost?")
    stream_graph_updates("what are the requirements?")
    print("Done")


# if __name__ == "__main__":
#     thread_id = uuid.uuid4()
#     config = {"configurable": {"thread_id": "1"}}

#     user_input = "How much does the semester cost at the uni?"

#     def stream_graph_updates(user_input):

#         prompt = get_prompt([("user", user_input)])
#         for event in graph.stream({"messages": prompt}, config=config):
#             for value in event.values():
#                 print("Assistant:", value["messages"][-1].content)

#     stream_graph_updates(user_input)

#     stream_graph_updates("yes i want to sign for the bachelors")
#     stream_graph_updates("how much does it cost?")
#     stream_graph_updates("what are the requirements?")
#     print("Done")
