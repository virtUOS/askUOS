import json
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from langchain.agents import (AgentExecutor, create_openai_tools_agent,
                              load_tools)
from langchain.agents.format_scratchpad import \
    format_to_openai_function_messages
from langchain.agents.format_scratchpad.openai_tools import \
    format_to_openai_tool_messages
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain.memory import ConversationBufferMemory
from langchain.memory.utils import get_prompt_input_key
from langchain.tools import Tool
from langchain.tools.retriever import create_retriever_tool
from langchain_core.agents import AgentActionMessageLog, AgentFinish
from langchain_core.callbacks import StdOutCallbackHandler
from langchain_core.exceptions import OutputParserException
from langchain_core.memory import BaseMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI

from db.vector_store import retriever
from settings import OPEN_AI_MODEL, SERVICE
from tools.search_web_tool import SearchUniWeb
from tools.uni_application_tool import application_instructions
from utils.language import prompt_language
from utils.prompt import get_prompt

# Define the prompt text based on the selected language
if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == 'English':
        from utils.prompt_text import prompt_text_english as prompt_text
    elif st.session_state["selected_language"] == 'Deutsch':
        from utils.prompt_text import prompt_text_deutsch as prompt_text
else:
    from utils.prompt_text import prompt_text_english as prompt_text




"""
TODO 
ConversationBufferMemory stores every message sent by the agent and the user (this is not optimal)
we should store only the messages that are relevant to the conversation --> ConversationSummaryMemory. The downside of this 
approach is that it uses an LLM to summarize the conversation which can be more expensive (when using the OpenAI API).
A solution could be to provide a local model for the summarization. 
ConversationBufferWindowMemory --> this allows to define a K parameter, where K is the number of interactions to remember.
the thing is that a small K could lead to the agent not being able to remember the context of the conversation.
"""



class Response(BaseModel):
    """Final response to the question being asked"""

    output: str = Field(description=prompt_text['response_output_description'])
    sources: List[str] = Field(
        description=prompt_text['response_sources_description']    
    )


def parse(message):

    # If no function was invoked, return to user
    if "function_call" not in message.additional_kwargs:
        return AgentFinish(return_values={"output": message.content}, log=message.content)

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
                answer = outputs['output']
                outputs= {}
                outputs['output'] = answer
                
           
       
            output_key = list(outputs.keys())[0]
        else:
            output_key = self.output_key
        return inputs[prompt_input_key], outputs[output_key]


        
class CampusManagementOpenAIToolsAgentBuilder:
    """
    Builder class that creates the objects needed to create the CampusManagementOpenAIToolsAgent.
    """
    def __init__(self):
        self._prompt = None
        self._llm = None
        self._tools = None
        self._memory = None

    def set_prompt(self, prompt: ChatPromptTemplate) -> 'CampusManagementOpenAIToolsAgentBuilder':
        self._prompt = prompt
        return self

    def set_llm(self, llm: ChatOpenAI) -> 'CampusManagementOpenAIToolsAgentBuilder':
        self._llm = llm
        return self

    def set_tools(self, tools: List[BaseTool]) -> 'CampusManagementOpenAIToolsAgentBuilder':
        self._tools = tools
        return self

    def set_memory(self, memory: BaseMemory) -> 'CampusManagementOpenAIToolsAgentBuilder':
        self._memory = memory
        return self

    def build(self) -> 'CampusManagementOpenAIToolsAgent':
        prompt = self._prompt or CampusManagementOpenAIToolsAgentBuilder.create_prompt()
        llm = self._llm or CampusManagementOpenAIToolsAgentBuilder.create_llm()
        tools = self._tools or CampusManagementOpenAIToolsAgentBuilder.create_tools()
        memory = self._memory or CampusManagementOpenAIToolsAgentBuilder.create_memory()
        return CampusManagementOpenAIToolsAgent(prompt, llm, tools, memory)

    @staticmethod
    def create_prompt() -> ChatPromptTemplate:
        from utils.prompt import get_prompt
        from utils.prompt_text import prompt_text_english as prompt_text
        return get_prompt(prompt_text)

    @staticmethod
    def create_llm() -> ChatOpenAI:
        handler = StdOutCallbackHandler()
        return ChatOpenAI(model=OPEN_AI_MODEL, temperature=0, callbacks=[handler])

    @staticmethod
    def create_tools() -> List[BaseTool]:
        return [
            create_retriever_tool(
                retriever,
                "technical_troubleshooting_questions",
                prompt_language()['description_technical_troubleshooting'],
            ),
            
            
            
            Tool(
                name='custom_university_web_search',
                func=SearchUniWeb.run(SERVICE),
                description=prompt_language()['description_university_web_search'],
                handle_tool_errors=True
            ),
        ]

    @staticmethod
    def create_memory() -> BaseMemory:
        return CustomSaveMemory(memory_key="chat_history", return_messages=True, k=5)


class CampusManagementOpenAIToolsAgent:
    """
    A class representing an agent for campus management using OpenAI tools.
    
    Args:
            prompt (Optional[ChatPromptTemplate]): The chat prompt template.
            llm (Optional[ChatOpenAI]): The language model used by the agent.
            tools (Optional[list[BaseTool]]): The list of tools used by the agent.
            memory (Optional[BaseMemory]): The memory used by the agent.
            

    Example:

    from agents.agent_openai_tools import CampusManagementOpenAIToolsAgent

    agent_executor = CampusManagementOpenAIToolsAgent.run()
    response = agent_executor('Hi, this is the user input')

    """

    def __init__(self, prompt: ChatPromptTemplate, llm: ChatOpenAI, tools: List[BaseTool], memory: BaseMemory):
        self.prompt = prompt
        self.llm = llm
        self.tools = tools
        self.memory = memory
        self._create_agent_executor()

    def _create_agent_executor(self):
        # agent = create_openai_tools_agent(self.llm, [*self.tools, load_tools(["human"])[0]], self.prompt)
        
        # TODO MAKE THIS GENERAL
        llm_with_tools = self.llm.bind_functions([*self.tools, load_tools(["human"])[0], Response])
        # llm_with_tools = self.llm.bind_functions([self.tools[0], self.tools[1], self.tools[2], Response])

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
            return_intermediate_steps=True,
            verbose=True,
            memory=self.memory,
            handle_parsing_errors=True,
            max_execution_time=30,  # Agent stops after 20 seconds
        )

    def __call__(self, input: str):
        response = self._agent_executor.invoke({"input": input})
        return response

    @classmethod
    def run(cls, **kwargs):
        builder = CampusManagementOpenAIToolsAgentBuilder()
        if 'prompt' in kwargs:
            builder.set_prompt(kwargs['prompt'])
        if 'llm' in kwargs:
            builder.set_llm(kwargs['llm'])
        if 'tools' in kwargs:
            builder.set_tools(kwargs['tools'])
        if 'memory' in kwargs:
            builder.set_memory(kwargs['memory'])
        return builder.build()





agent_executor = CampusManagementOpenAIToolsAgent.run(prompt=get_prompt(prompt_text))


if __name__ == "__main__":
    
    agent_executor = CampusManagementOpenAIToolsAgent.run()
    # testing memory 
    # agent_executor('can i study law?')            
    # agent_executor('how long does the master take?')
    # agent_executor('how long does the bachelor take?')
    
    instructions = ['1. Visit the Online-Bewerbungsportal (online application portal) on the university\'s website.', '2. Review the application deadlines and requirements for your desired program.', '3. Complete the online application form and submit the required documents.', '4. Keep track of the application status and any additional steps required.']

    
    agent_inter = agent_executor._agent_executor.iter({"input": 'guide me through the application process?'})
    
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
        
    