import asyncio
import threading
import uuid
from collections import deque
from typing import ClassVar, Dict, List, Literal, Optional, Union

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
)
from langchain_core.prompts import PromptTemplate

# from langchain_core.pydantic_v1 import BaseModel, Field, PrivateAttr
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from pydantic import Field
from src.chatbot.agents.utils.agent_helpers import llm_gemini, llm_optional
from src.chatbot.prompt.main import (
    get_prompt_length,
    get_system_prompt,
    translate_prompt,
)
from src.chatbot.tools.utils.tool_helpers import ReferenceRetriever
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings
from dataclasses import dataclass
from src.chatbot.agents.graph_node_edges import GraphEdgesMixin, GraphNodesMixin, State

OPEN_AI_MODEL = settings.model.model_name
DEBUG = settings.application.debug
# message history limit within the graph
MESSAGE_HISTORY_LIMIT = 7
# Maximum number of tokens for the conversation summary
MAX_TOKEN_SUMMARY = 1000

REDIS_DB_URI = "redis://redis:6379"

class CampusManagementOpenAIToolsAgent(GraphNodesMixin, GraphEdgesMixin):

    # Singleton instance
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, **data):
        # data: key-value pairs passed through the run method, e.g., CampusManagementOpenAIToolsAgent.run(language='Deutsch')
        if not self._initialized:
            
            self._llm_optional = llm_optional()
            self._llm = llm_gemini()
            
            self.language: str = Field(default=settings.language)
            # TODO should not be a private attribute
            self._graph: StateGraph = None
            self._chat_history: List[Dict] = []
            self._prompt_length: int = None
            self._agent_direct_msg: str = None
            self._visited_links: List[str] = None
            self._visited_docs: ReferenceRetriever = ReferenceRetriever()

            ###----Redis -----######
            # Create the checkpointer (keeps connection alive)
            self._checkpointer = None
            self._checkpointer_context = AsyncRedisSaver.from_conn_string(
                "redis://redis:6379"
            )  # The context manager (for cleanup)
            ###----Redis -----######

            tools = GraphNodesMixin.create_tools()
            self._tools_by_name = {tool.name: tool for tool in tools}
            # important: the code uses function calling as opposed to tool calling. (DEPENDS ON THE MODEL and how it was fine tuned)
            self._llm_with_tools = self._llm.bind_tools(tools)
            # self._llm_with_tools = self._reasoning_llm.bind_tools(tools)
            self._prompt_length = get_prompt_length()
            self._initialized = True

    async def cleanup(self):
        if self._checkpointer_context and self._initialized:
            await self._checkpointer_context.__aexit__(None, None, None)
            self._checkpointer = None
            self._checkpointer_context = None
            self._initialized = False
            print("✅ Agent cleanup complete")

    def shorten_conversation_summary(self, summary: str) -> str:
        """Shorten the conversation summary if it exceeds the maximum token limit."""

        logger.warning(
            f"[LANGGRAPH][SHORTEN CONVERSATION SUMMARY] Summary length: {len(summary)}"
        )
        template = translate_prompt()["shorten_conversation_summary"]

        prompt = PromptTemplate(template=template, input_variables=["summary"])
        chain = prompt | self._llm_optional

        response = chain.invoke({"summary": summary})

        return response

    def summarize_conversation(
        self, messages: List[BaseMessage], previous_summary: str = None
    ) -> str:
        # TODO only summarize if the AI message is greater than a certain number of tokens

        if previous_summary:
            template = translate_prompt()["summarize_conversation_previous"]
        else:
            template = translate_prompt()["summarize_conversation"]

        prompt = PromptTemplate(
            template=template, input_variables=["messages", "previous_summary"]
        )
        chain = prompt | self._llm_optional

        # Prepare the arguments based on previous_summary availability
        invoke_args = {"messages": messages}
        if previous_summary:
            invoke_args["previous_summary"] = previous_summary

        response = chain.invoke(invoke_args)
        # google models
        response_text = response.text
        # openai
        # response_text = response.content
        tokens_response = self._llm_optional.get_num_tokens(response_text)
        # To prevent the conversation summary from being too long, we can shorten it
        if tokens_response > MAX_TOKEN_SUMMARY:

            logger.warning(
                f"Conversation Summary is too long ({tokens_response} tokens)"
            )
            response = self.shorten_conversation_summary(response_text)

        return f"**Summary of conversation earlier:** {response_text}"

    async def _create_graph(self):
        graph_builder = StateGraph(State)

        graph_builder.add_node("agent_node", self.agent_node)

        graph_builder.add_node("tool_node", self.tool_node)
        graph_builder.add_node("judge_node", self.judge_node)
        graph_builder.add_node("rewrite", self.rewrite)  # Re-writing the question
        graph_builder.add_node(
            "generate", self.generate
        )  # Generating a response after we know the documents are relevant
        # Call agent node to decide to retrieve or not
        graph_builder.add_node("generate_application", self.generate_application)
        graph_builder.add_node(
            "generate_teaching_degree_node", self.generate_teaching_degree_node
        )
        # graph_builder.add_node("judge_answer", self.juge_answer)
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
            {
                "generate": "generate",
                "rewrite": "rewrite",
                "generate_application": "generate_application",
                "generate_teaching_degree_node": "generate_teaching_degree_node",
            },
        )
        graph_builder.add_edge("generate", END)
        graph_builder.add_edge("rewrite", "agent_node")
        graph_builder.add_edge("generate_application", END)
        graph_builder.add_edge("generate_teaching_degree_node", END)

        self._checkpointer = await self._checkpointer_context.__aenter__()
        self._graph = graph_builder.compile(
            debug=DEBUG, checkpointer=self._checkpointer
        )

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

    async def _generate_graph(self):
        # TODO check for race conditions
        if self._graph is None:
            await self._create_graph()

    # @classmethod
    # def run(cls, *args, **kwargs) -> "CampusManagementOpenAIToolsAgent":
    #     """Create and return an instance of the agent.

    #     Returns:
    #         CampusManagementOpenAIToolsAgent: Configured agent instance
    #     """
    #     instance = cls(*args, **kwargs)
    #     return instance


if __name__ == "__main__":
    from src.chatbot.prompt.main import get_system_prompt
    from src.chatbot.prompt.prompt_date import get_current_date

    graph = CampusManagementOpenAIToolsAgent()

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

    # print_graph(graph._graph)
    async def _execute_graph():
        await graph._generate_graph()
        thread_id = uuid.uuid4()
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.application.recursion_limit,  # This amounts to two laps of the graph # https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
        }
        current_date = get_current_date(settings.language.lower())
        conversation_summary = ""
        # history = [HumanMessage(content="Wo liegt der NC bei Sport?")]
        # user_input = "Wo liegt der NC bei Sport?",
        history = [HumanMessage(content="hi")]
        user_input = "hi",
        # list of system, ai and human messages
        system_user_prompt = get_system_prompt(
            conversation_summary, history, user_input, current_date
        )
        response = await graph._graph.ainvoke(
            {
            "messages": system_user_prompt,
            "message_history": history,
            "user_initial_query": user_input,
            "current_date": current_date,
            },
            config=config,
        )
        print()

    asyncio.run(_execute_graph())

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
