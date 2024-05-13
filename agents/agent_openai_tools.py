from typing import Optional
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



"""
TODO 
ConversationBufferMemory stores every message sent by the agent and the user (this is not optimal)
we should store only the messages that are relevant to the conversation --> ConversationSummaryMemory. The downside of this 
approach is that it uses an LLM to summarize the conversation which can be more expensive (when using the OpenAI API).
A solution could be to provide a local model for the summarization. 
ConversationBufferWindowMemory --> this allows to define a K parameter, where K is the number of interactions to remember.
the thing is that a small K could lead to the agent not being able to remember the context of the conversation.
"""





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
            self._memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)
  
    def _create_agent_executor(self):
        """
        Creates the agent executor for the agent.
        """
        agent = create_openai_tools_agent(self._llm, self._tools, self._prompt)

        self._agent_executor = AgentExecutor(agent=agent,
                               tools=self.tools,
                               verbose=True,
                               memory=self.memory,
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

