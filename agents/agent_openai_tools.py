from typing import Optional, List, Dict, Any, Tuple
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools.retriever import create_retriever_tool
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from tools.search_web_tool import  SearchUniWeb
from langchain.memory import ConversationBufferMemory
import streamlit as st
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from utils.language import prompt_language
from settings import SERVICE, OPEN_AI_MODEL
from db.vector_store import retriever
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.memory import BaseMemory
from langchain_core.tools import BaseTool
from langchain_core.agents import AgentActionMessageLog, AgentFinish
from langchain.agents.format_scratchpad import format_to_openai_function_messages
import json
from langchain.memory.utils import get_prompt_input_key




"""
TODO 
ConversationBufferMemory stores every message sent by the agent and the user (this is not optimal)
we should store only the messages that are relevant to the conversation --> ConversationSummaryMemory. The downside of this 
approach is that it uses an LLM to summarize the conversation which can be more expensive (when using the OpenAI API).
A solution could be to provide a local model for the summarization. 
ConversationBufferWindowMemory --> this allows to define a K parameter, where K is the number of interactions to remember.
the thing is that a small K could lead to the agent not being able to remember the context of the conversation.
"""



def parse(output):
    # If no function was invoked, return to user
    if "function_call" not in output.additional_kwargs:
        return AgentFinish(return_values={"output": output.content}, log=output.content)

    # Parse out the function call
    function_call = output.additional_kwargs["function_call"]
    name = function_call["name"]
    inputs = json.loads(function_call["arguments"])

    # If the Response function was invoked, return to the user with the function inputs
    if name == "Response":
        return AgentFinish(return_values=inputs, log=str(function_call))
    # Otherwise, return an agent action
    else:
        return AgentActionMessageLog(
            tool=name, tool_input=inputs, log="", message_log=[output]
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


        


class Response(BaseModel):
    """Final response to the question being asked"""

    output: str = Field(description="The final answer to respond to the user")
    sources: List[str] = Field(
        description="The sources used to find the answer, it should be a list of URLs. Only include this field if the answer is based on external sources obtain from the web"
    )



class CampusManagementOpenAIToolsAgent:
    """
    A class representing an agent for campus management using OpenAI tools.

    Example:

    from agents.agent_openai_tools import CampusManagementOpenAIToolsAgent

    agent_executor = CampusManagementOpenAIToolsAgent.run()
    response = agent_executor('Hi, this is the user input')

    """

    def __init__(self,
                 prompt: Optional[ChatPromptTemplate] =None,
                 llm: Optional[ChatOpenAI]=None, 
                 memory: Optional[BaseMemory]=None,
                 tools:  Optional[list [BaseTool]]=None):
        """
        Initialize the CampusManagementOpenAIToolsAgent.

        Args:
            prompt (Optional[ChatPromptTemplate]): The chat prompt template.
            llm (Optional[ChatOpenAI]): The language model used by the agent.
            memory (Optional[BaseMemory]): The memory used by the agent.
            tools (Optional[list[BaseTool]]): The list of tools used by the agent.
        """
        self.prompt = prompt
        self.llm = llm 
        self.tools = tools
        self.memory = memory
        self._create_agent_executor()

    @property
    def prompt(self):
        """
        Get the chat prompt template.
        """
        return self._prompt

    @prompt.setter
    def prompt(self, value):
        """
        Set the chat prompt template.

        Args:
            value: The chat prompt template.
        """
        if value:
            self._prompt = value
        else:
          
            from utils.prompt import get_prompt
            from utils.prompt_text import prompt_text_english as prompt_text
            prompt=get_prompt(prompt_text)
            self._prompt = prompt
    
    @property
    def llm(self):
        """
        Get the language model used by the agent.
        """
        return self._llm

    @llm.setter
    def llm(self, value):
        """
        Set the language model used by the agent.

        Args:
            value: The language model used by the agent.
        """
        if value:
            self._llm = value
        else:
            self._llm = ChatOpenAI(model=OPEN_AI_MODEL, temperature=0)   
    
    @property
    def tools(self):
        """
        Get the list of tools used by the agent.
        """
        return self._tools

    @tools.setter
    def tools(self, value):
        """
        Set the list of tools used by the agent.

        Args:
            value: The list of tools used by the agent.
        """
        if value:
            self._tools = value
        else:

            self._tools =[
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
                ),]
    
    @property
    def memory(self):
        """
        Get the memory used by the agent.
        """
        return self._memory

    @memory.setter
    def memory(self, memory):
        """
        Set the memory used by the agent.

        Args:
            memory: The memory used by the agent.
        """
        if memory:
            self._memory = memory
        else:
            self._memory = CustomSaveMemory(memory_key="chat_history", return_messages=True, k=5)
            # self._memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)
  
    def _create_agent_executor(self):
        """
        Creates the agent executor for the agent.
        """
        # agent = create_openai_tools_agent(self._llm, self._tools, self._prompt)
        
        llm_with_tools = self._llm.bind_functions([self._tools[0],self._tools[1], Response])
        
        agent = (
                    {
                        "input": lambda x: x["input"],
                        # Format agent scratchpad from intermediate steps
                        "agent_scratchpad": lambda x: format_to_openai_function_messages(
                            x["intermediate_steps"]
                        ),
                    }
                    | self._prompt
                    | llm_with_tools
                    | parse
                )
                        

        self._agent_executor = AgentExecutor(agent=agent,
                               tools=self._tools,
                               verbose=True,
                               memory=self._memory,
                               handle_parsing_errors=True,
                               max_execution_time=20, # Agent stops after 20 seconds
                               )
 
    def __call__(self, input: str):
        """
        Invoke the agent with the given input.

        Args:
            input: The input to the agent.

        Returns:
            The response from the agent.
        """
        response = self._agent_executor.invoke({"input": input})
        return response

    @classmethod
    def run(cls,**kwargs):
        """
        Run the agent with the given keyword arguments.

        Args:
            kwargs: The keyword arguments.

        Returns:
            The instance of the agent.
        """
        return cls(**kwargs)







if __name__ == "__main__":

    from langchain.callbacks import get_openai_callback
    from utils.prompt import prompt


    def count_tokens(agent_ex, input):
            with get_openai_callback() as cb:
                result = agent_ex.invoke({'input':input})
                print(f'Spent a total of {cb.total_tokens} tokens')

            return result

    agent_executor = CampusManagementOpenAIToolsAgent.run()

    response = agent_executor({"input": 'Richtlinie der Universität Osnabrück für die Vergabe von Deutschlandstipendien'}) # should return the pdf
    response = agent_executor({"input": 'Abschlussnote Psychologiestudium Osnabrueck'})
    # response = count_tokens(agent_executor, 'muss ich das Einverständnis meiner Eltern haben?')
    response =agent_executor({"input": 'where is the university'})
    response = agent_executor({"input": 'what is the application process'})
    response = agent_executor({"input": 'what is the application deadline'})
    response = agent_executor({"input": 'how much does it cost?'})
    print()

