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


from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

OPEN_AI_MODEL = settings.model.model_name


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


graph_builder = StateGraph(State)

llm = ChatOpenAI(
    model=OPEN_AI_MODEL,
    temperature=0,
)


def chatbot(state: State):
    return {"messages": [llm.invoke(state["messages"])]}


graph_builder.add_node("chatbot", chatbot)


graph_builder.add_edge(START, "chatbot")

graph_builder.add_edge("chatbot", END)

graph = graph_builder.compile()


if __name__ == "__main__":

    user_input = "What do you know about LangGraph?"

    def stream_graph_updates(user_input):

        prompt = get_prompt([("user", user_input)])
        for event in graph.stream({"messages": prompt}):
            for value in event.values():
                print("Assistant:", value["messages"][-1].content)

    stream_graph_updates(user_input)
    print("Done")
