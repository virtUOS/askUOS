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
import redis.asyncio as aioredis
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
                    cls._instance._async_initialized = False
        return cls._instance

    def __init__(self, **data):
        # data: key-value pairs passed through the run method, e.g., CampusManagementOpenAIToolsAgent.run(language='Deutsch')
        if not self._initialized:
            
            self._llm_optional = llm_optional()
            self._llm = llm_gemini()
            
            self.language: str = Field(default=settings.language)
            self._graph: StateGraph = None
            self._chat_history: List[Dict] = []
            self._prompt_length: int = None
            self._agent_direct_msg: str = None
            self._visited_links: List[str] = None
            self._visited_docs: ReferenceRetriever = ReferenceRetriever()

            ###----Redis -----######
            # Create the checkpointer (keeps connection alive)
            self._checkpointer: AsyncRedisSaver = None  # initialized later in async context

            ###----Redis -----######

            tools = GraphNodesMixin.create_tools()
            self._tools_by_name = {tool.name: tool for tool in tools}
            # important: the code uses function calling as opposed to tool calling. (DEPENDS ON THE MODEL and how it was fine tuned)
            self._llm_with_tools = self._llm.bind_tools(tools)
            # self._llm_with_tools = self._reasoning_llm.bind_tools(tools)
            self._prompt_length = get_prompt_length()
            self._initialized = True

    async def _ensure_async_initialized(self):
        """
        Lazily initialize async resources (Redis checkpointer + graph).
        Safe to call multiple times — only runs once.
        """
        if self._async_initialized:
            return

        self._checkpointer = AsyncRedisSaver(
        redis_url=REDIS_DB_URI,
        ttl = {
            "default_ttl":120, # 2 hours/ 120 minutes
            "refresh_on_read": True
        }
        )
        await self._checkpointer.asetup()

        # Now build the graph once
        await self._create_graph()

        self._async_initialized = True
    
    async def cleanup(self):
        """Call this on application shutdown."""
        if self._checkpointer is not None:
            # AsyncRedisSaver manages its own internal Redis connection
            if hasattr(self._checkpointer, "_redis") and self._checkpointer._redis:
                await self._checkpointer._redis.aclose()
            self._checkpointer = None
        self._async_initialized = False
        self._graph = None


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
    # clear cash for testing purposes
    async def clear_cache():
        redis_client = aioredis.Redis(host="redis", port=6379, decode_responses=True)
        try:
            await redis_client.flushall()
            await redis_client.aclose()
        except Exception as e:
            print(f"Failed to clear Redis cache: {e}")
    # print_graph(graph._graph)
    async def _execute_graph():
        # make sure redis connection is not close before creating the graph
        #await clear_cache()
        await graph._ensure_async_initialized()
        #thread_id = uuid.uuid4()
        thread_id = 1
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.application.recursion_limit,  # This amounts to two laps of the graph # https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
        }
        current_date = get_current_date(settings.language.lower())
        user_input = "hi, Im bob",
     
        response = await graph._graph.ainvoke(
            {
            "messages": [HumanMessage(content=user_input)], # Only the HumanMessage goes into state (and gets checkpointed)
            "user_initial_query": user_input, # used by agent node only and added to the system prompt
            "current_date": current_date,
            },
            config=config,
        )
        print()
        user_input = "who am i?"
        response = await graph._graph.ainvoke(
            {
            "messages": [HumanMessage(content=user_input)],
            #"message_history": history, # used by agent node only
            "user_initial_query": user_input, # used by agent node only and added to the system prompt
            "current_date": current_date,
            },
            config=config,
        )
        print()
        user_input = "who are you?",
        response = await graph._graph.ainvoke(
            {
            "messages": [HumanMessage(content=user_input)], # used by agent node only
            #"message_history": history, # used by agent node only
            "user_initial_query": user_input, # used by agent node only and added to the system prompt
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
