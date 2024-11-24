import json
from json import JSONDecodeError
from typing import Any, ClassVar, Dict, List, Optional, Tuple

import streamlit as st
from langchain.agents import AgentExecutor, load_tools
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
from src.chatbot.utils.prompt import get_prompt, translate_prompt, get_prompt_length
from src.chatbot_log.chatbot_logger import logger
from src.chatbot.utils.agent_helpers import llm

OPEN_AI_MODEL = settings.model.model_name


"""
TODO 
ConversationBufferMemory stores every message sent by the agent and the user (this is not optimal)
we should store only the messages that are relevant to the conversation --> ConversationSummaryMemory. The downside of this 
approach is that it uses an LLM to summarize the conversation which can be more expensive (when using the OpenAI API).
A solution could be to provide a local model for the summarization. 
ConversationBufferWindowMemory --> this allows to define a K parameter, where K is the number of interactions to remember.
the thing is that a small K could lead to the agent not being able to remember the context of the conversation.
"""


# TODO this class depends on streamlit. It should be refactored to remove the dependency on streamlit (there should be a separation of concerns)
class CallbackHandlerStreaming(StreamingStdOutCallbackHandler):
    """
    CallbackHandlerStreaming is a handler class that processes tokens generated by a language model (LLM) in a streaming fashion.

    """

    def __init__(self):
        self.content: str = ""

    def on_llm_new_token(self, token: str, **kwargs: any) -> None:
        # runs for every token generated by the LLM
        if token:
            # streaming of every line
            if "\n" in token:
                self.content += token
                st.markdown(self.content)
                self.content = ""
            else:
                self.content += token

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> Any:
        """Run on agent end."""
        if self.content:
            # if there is content left, stream it
            st.markdown(self.content)
            self.content = ""


# class Response(BaseModel):
#     """Final response to the question being asked"""

#     prompt_text = translate_prompt()
#     output: str = Field(description=prompt_text["response_output_description"])
#     sources: List[str] = Field(description=prompt_text["response_sources_description"])


def parse(message):

    # If no function was invoked, return to user
    if "function_call" not in message.additional_kwargs:
        return AgentFinish(
            return_values={"output": message.content}, log=message.content
        )

    # Parse out the function call
    # additional_kwargs= {'function_call': {'arguments': '{{"output":""..."", "sources"}, 'name': '...'}' } }
    function_call = message.additional_kwargs["function_call"]
    function_name = function_call["name"]

    try:
        inputs = json.loads(function_call["arguments"] or "{}")
    except JSONDecodeError:
        raise OutputParserException(
            f"Could not parse tool input: {function_call} because "
            f"the `arguments` is not valid JSON."
        )

    if "__arg1" in inputs:
        tool_input = inputs["__arg1"]
    else:
        tool_input = inputs

    content_msg = f"responded: {message.content}\n" if message.content else "\n"
    log = f"\nInvoking: `{function_name}` with `{tool_input}`\n{content_msg}\n"

    print(log)
    # If the Response function was invoked, return to the user with the function inputs
    if function_name == "Response":
        return AgentFinish(return_values=inputs, log=str(function_call))
    # Otherwise, return an agent action
    else:
        return AgentActionMessageLog(
            tool=function_name, tool_input=inputs, log=log, message_log=[message]
        )


class CustomSaveMemory(ConversationBufferWindowMemory):
    def _get_input_output(
        self, inputs: Dict[str, Any], outputs: Dict[str, str]
    ) -> Tuple[str, str]:
        if self.input_key is None:
            prompt_input_key = get_prompt_input_key(inputs, self.memory_variables)
        else:
            prompt_input_key = self.input_key
        if self.output_key is None:
            if len(outputs) != 1:
                # if 'sources' in outputs:
                #     sources = ', '.join(outputs['sources'])
                # outputs['output'] = outputs['output'] + f'\nSources: {sources}'
                answer = outputs["output"]
                outputs = {}
                outputs["output"] = answer

            output_key = list(outputs.keys())[0]
        else:
            output_key = self.output_key
        return inputs[prompt_input_key], outputs[output_key]


class Defaults:
    @staticmethod
    def create_prompt() -> ChatPromptTemplate:
        """
        Creates a chatbot prompt using the `get_prompt` function.

        Returns:
            ChatPromptTemplate: The generated chatbot prompt.
        """

        return get_prompt()

    @staticmethod
    def create_llm() -> ChatOpenAI:
        """
        Creates a ChatOpenAI instance with the specified model, temperature, streaming, and callbacks.

        Returns:
            ChatOpenAI: The created ChatOpenAI instance.
        """

        # handler = StdOutCallbackHandler()
        # return ChatOpenAI(
        #     model=OPEN_AI_MODEL,
        #     temperature=0,
        #     streaming=True,
        #     callbacks=[StdOutCallbackHandler()],
        # )
        return llm()

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
                translate_prompt()["description_technical_troubleshooting"],
            ),
            StructuredTool.from_function(
                name="custom_university_web_search",
                func=search_uni_web.run,
                description=translate_prompt()["description_university_web_search"],
                handle_tool_errors=True,
            ),
        ]

    @staticmethod
    def create_memory() -> BaseMemory:
        """
        Creates a memory object for the chatbot agent.

        Returns:
            BaseMemory: The created memory object.
        """
        return CustomSaveMemory(memory_key="chat_history", return_messages=True, k=5)


class CampusManagementOpenAIToolsAgent(BaseModel):
    """
    A class representing an agent for campus management using OpenAI tools.

    Args:
            prompt (Optional[ChatPromptTemplate]): The chat prompt template.
            language (Optional[str]): The language chosen by the user and subsequtly used by the agent.
            llm (Optional[ChatOpenAI]): The language model used by the agent.
            tools (Optional[list[BaseTool]]): The list of tools used by the agent.
            memory (Optional[BaseMemory]): The memory used by the agent.


    Example:

    from agents.agent_openai_tools import CampusManagementOpenAIToolsAgent

    agent_executor = CampusManagementOpenAIToolsAgent.run() # run with default values
    agent_executor = CampusManagementOpenAIToolsAgent.run(prompt=some_prompt, llm=some_llm, tools=some_tools, memory=some_memory)
    response = agent_executor('Hi, are you an AI?') # ask the agent a question

    """

    # Singleton instance
    _instance: ClassVar[Optional["CampusManagementOpenAIToolsAgent"]] = None

    prompt: ChatPromptTemplate = Field(default_factory=Defaults.create_prompt)
    prompt_length: int = Field(default_factory=get_prompt_length)
    language: Optional[str] = None
    llm: ChatOpenAI = Field(default_factory=Defaults.create_llm)
    tools: List[BaseTool] = Field(default_factory=Defaults.create_tools)
    memory: BaseMemory = Field(default_factory=Defaults.create_memory)

    # (not part of the model schema)
    _agent_executor: AgentExecutor = PrivateAttr(default=None)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CampusManagementOpenAIToolsAgent, cls).__new__(cls)
            logger.info("Creating a new instance of CampusManagementOpenAIToolsAgent")

        # create a new instance if the language changes
        elif (
            hasattr(cls._instance, "language")
            and cls._instance.language != settings.language
        ):  # TODO dependency injection (settings)
            # TODO preserve the memory of the previous agent (when the language changes and a previous conversation is still ongoing)
            cls._instance = super(CampusManagementOpenAIToolsAgent, cls).__new__(cls)
            logger.info("Creating a new instance of CampusManagementOpenAIToolsAgent")

        return cls._instance

    def __init__(self, **data):
        if not self.__dict__:
            super().__init__(**data)
            self.language = settings.language
            logger.info(f"Language set to: {self.language}")
            self._create_agent_executor()

    def _create_agent_executor(self):

        llm_with_tools = self.llm.bind_functions(
            [*self.tools, load_tools(["human"])[0]]
        )

        agent = (
            {
                "input": lambda x: x["input"],
                "chat_history": lambda x: x["chat_history"],
                "agent_scratchpad": lambda x: format_to_openai_function_messages(
                    x["intermediate_steps"]
                ),
            }
            | self.prompt
            | llm_with_tools
            | parse
        )

        self._agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            return_intermediate_steps=False,
            verbose=True,
            memory=self.memory,
            handle_parsing_errors=True,
            max_execution_time=60,  # Agent stops after 60 seconds
        )

    def compute_internal_tokens(self, query: str) -> int:
        # extract the chathistory from the memory
        # TODO this is a list, iterate over the list and extract the content
        # TODO BUG: Agent's scratchpad tokens are not being counted (fix sum(count_tokens_history) * 2)
        history = self._agent_executor.memory.dict()["chat_memory"][
            "messages"
        ]  # this is a list [{'content':'', 'additional_kwargs':{},...}, {}...]

        count_tokens_history = [self.llm.get_num_tokens(c["content"]) for c in history]
        # TODO multiply by 2 to account for agent's scratchpad # TODO FIX THIS (THIS IS NOT THE CORRECT WAY TO COUNT (SCRATCHPAD) TOKENS)
        internal_tokens = (
            sum(count_tokens_history) * 2
            + self.prompt_length
            + self.llm.get_num_tokens(query)
        )
        return internal_tokens

    def compute_search_num_tokens(self, search_result_text: str) -> int:

        search_result_text_tokens = self.llm.get_num_tokens(search_result_text)

        return search_result_text_tokens

    def __call__(self, input: str):

        config = {"callbacks": [CallbackHandlerStreaming()]}
        response = self._agent_executor.invoke({"input": input}, config=config)
        return response

    @classmethod
    def run(cls, **kwargs):

        instance = cls(**kwargs)

        # TODO make sure there is only one instance of the agent in the memory (check all objects in the memory with type CampusManagementOpenAIToolsAgent)
        return instance


if __name__ == "__main__":

    agent_executor = CampusManagementOpenAIToolsAgent.run()
    # testing memory
    # agent_executor('can i study law?')
    # agent_executor('how long does the master take?')
    # agent_executor('how long does the bachelor take?')

    instructions = [
        "1. Visit the Online-Bewerbungsportal (online application portal) on the university's website.",
        "2. Review the application deadlines and requirements for your desired program.",
        "3. Complete the online application form and submit the required documents.",
        "4. Keep track of the application status and any additional steps required.",
    ]

    agent_inter = agent_executor._agent_executor.iter(
        {"input": "guide me through the application process?"}
    )

    for step in agent_inter:
        if output := step.get("intermediate_step"):
            action, value = output[0]

            # here i could do something like: if the tool is custom_university_web_search,  and the value is  'Content not found' or 'Failed to fetch content', repeat the serach with different query or ask
            # a follow up question to the user.
            if action.tool == "application_instructions":
                for instruction in instructions:
                    print(instruction)
                    _continue = input("Should the agent continue (Y/n)?:\n") or "Y"
                    if _continue.lower() != "y":
                        break

            # Ask user if they want to continue
            # _continue = input("Should the agent continue (Y/n)?:\n") or "Y"
            # if _continue.lower() != "y":
            #     break
    print()
