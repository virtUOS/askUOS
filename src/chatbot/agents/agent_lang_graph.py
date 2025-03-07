import json
import uuid
from collections import deque
from typing import Annotated, ClassVar, Dict, List, Literal, Optional

import streamlit as st
from langchain.tools.retriever import create_retriever_tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field, PrivateAttr
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from src.chatbot.db.clients import get_retriever
from src.chatbot.prompt.main import get_prompt
from src.chatbot.tools.utils.tool_helpers import visited_docs
from src.chatbot.utils.agent_helpers import llm
from src.chatbot.utils.agent_retriever import RetrieverInput, _get_relevant_documents
from src.chatbot.utils.prompt import get_prompt_length, translate_prompt
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

OPEN_AI_MODEL = settings.model.model_name
DEBUG = settings.application.debug


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]
    search_query: Optional[list]  # query used to search the web or db
    user_initial_query: Optional[str]  # user's initial query
    answer_rejection: Optional[str]


class GraphEdgesMixin:
    def route_tools(
        self,
        state: State,
    ) -> Literal["tool_node", END]:
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
        return "judge_node"

    def route_end(self, state: State):
        if state["pass_hallucinate_check"] == "no":
            return "agent_node"
        return END

    def grade_documents(self, state) -> Literal["generate", "rewrite"]:
        """
        Determines whether the retrieved documents are relevant to the question.

        Args:
            state (messages): The current state

        Returns:
            str: A decision for whether the documents are relevant or not
        """

        messages = state["messages"]

        tool_message = [i for i in messages if isinstance(i, ToolMessage)]
        # get the last tool message
        tool_message = tool_message[-1] if tool_message else None

        # TODO if the bot asks something back, and the user says 'yes', then 'yes' is not the actual user query
        # TODO but rather the query used by the tool node.

        tool_query = " ".join(state["search_query"])

        # Data model
        class grade(BaseModel):
            """Binary score for relevance check."""

            binary_score: str = Field(
                description=translate_prompt(settings.language)["grader_binary_score"]
            )

        llm_with_str_output = self._llm.with_structured_output(grade)

        # Prompt
        prompt = PromptTemplate(
            template=translate_prompt(settings.language)["grading_llm"],
            input_variables=["context", "question"],
        )

        # Chain
        chain = prompt | llm_with_str_output

        scored_result = chain.invoke(
            {"question": tool_query, "context": tool_message.content}
        )

        score = scored_result.binary_score
        score = score.lower()
        if score == "yes" or score == "ja":
            logger.debug("---DECISION: DOCS RELEVANT---")
            return "generate"

        else:
            logger.debug("---DECISION: DOCS NOT RELEVANT---")
            return "rewrite"

    def judge_agent_decision(self, state: State):

        class judgement(BaseModel):

            judgement_binary: Literal["yes", "no"] = Field(
                description="""
                The agent must use a Tool 'yes', or 'no'
                """
            )
            reason: str = Field(
                description="Back up your decision with a short explanation"
            )

        llm_with_str_output = self._llm.with_structured_output(judgement)
        prompt = PromptTemplate(
            template="""
            You are to act as a judge. Your task is to assess whether an agent's decision not to use a tool is appropriate.

            The agent must use the tools at its disposal to address user queries, the agent should not answer questions based on its training knowledge.
            Exceptions are only when the agent needs to ask clarification questions to the user or when the agent greets the user back.
            Assessment Task:

            The agent has decided not to use a tool.
            Is the agent's decision correct?
            Provide a binary score 'yes' or 'no': 
                - 'no', the agent must have used a tool, hence the agent is wrong.
                - 'yes', the agent is right, there was not need to a use a tool. 
            Provide a reason for your decision. 
            Below, you will find the agent's message and the user's query:

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

        if score.judgement_binary == "yes":
            print(state["messages"][-1].content)
            return END
        else:

            msg = [HumanMessage(content=score.reason)]
            # state["answer_rejection"] = score.reason
            state["messages"] = msg

            return "agent_node"


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
    def filter_messages(messages: List, k: int):
        # TODO make sure that the system message is always kept

        if len(messages) <= k:
            return messages
        return messages[-k:]

    # Nodes
    def agent_node(self, state: State):
        # TODO if a tool was called, only pass the tool message, system message and human messageS
        messages = GraphNodesMixin.filter_messages(state["messages"], 7)
        # TODO pass callback to the llm_with_tools object, to detect when the tokens are generated and stream them
        # detect when AI message contains 'finish_reason':'stop' and start streaming the tokens

        reponse = self._llm_with_tools.invoke(messages)
        return {
            "messages": [reponse],
            "search_query": [],
        }

    def judge_node(self, state: State):

        # msg = [HumanMessage(content=state["answer_rejection"])]

        return None

    def tool_node(self, inputs: dict):
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
        return {"messages": outputs, "search_query": search_query}

    def rewrite(self, state):
        """
        Transform the query to produce a better question.

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

    def generate(self, state):
        """
        Generate answer

        Args:
            state (messages): The current state

        Returns:
            dict: The updated state with re-phrased question
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
            # self._llm_answer_grader = self._llm.with_structured_output(GradeAnswer)

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
    from src.chatbot.prompt.main import get_prompt

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

    thread_id = uuid.uuid4()
    config = {
        "configurable": {"thread_id": thread_id},
    }

    user_input = "How can i change the password of my stud.ip account?"
    # user_input = "Tell me about the biology program?"
    prompt = get_prompt([("user", user_input)])

    response = graph._graph.invoke({"messages": prompt}, config=config)

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


# "As a grader, your task is to evaluate whether an LLM generated answer effectively addresses and resolves a user's query while being based on the retrieved information. Assign a binary score:
# 'yes' if the answer fulfills both criteria (it resolves the user query
# and is grounded in the retrieved information) or 'no' if it fails to meet either or both criteria."
