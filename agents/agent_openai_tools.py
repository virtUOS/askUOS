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



# TODO change model to gpt-3.5-turbo
# llm = ChatOpenAI(model="gpt-3.5-turbo-1106", temperature=0)

# create tools


    

class CampusManagementOpenAIToolsAgent:
    """
    A custom agent that utilizes OpenAI tools for generating responses.

    Args:
        prompt (str, optional): The initial prompt for the agent. Defaults to None.
        llm (ChatOpenAI, optional): The language model to be used by the agent. Defaults to None.
        memory (ConversationBufferWindowMemory, optional): The memory to store conversation history. Defaults to None.
        tools (list, optional): The list of tools to be used by the agent. Defaults to None.

    Attributes:
        prompt (str): The initial prompt for the agent.
        llm (ChatOpenAI): The language model used by the agent.
        memory (ConversationBufferWindowMemory): The memory to store conversation history.
        tools (list): The list of tools used by the agent.
    """

    def __init__(self,
                 prompt=None,
                 llm=None, 
                 memory=None,
                 tools=None):
        """
        Initializes a new instance of the CustomOpenAIToolsAgent class.

        Args:
            prompt (str, optional): The initial prompt for the agent. Defaults to None.
            llm (ChatOpenAI, optional): The language model to be used by the agent. Defaults to None.
            memory (ConversationBufferWindowMemory, optional): The memory to store conversation history. Defaults to None.
            tools (list, optional): The list of tools to be used by the agent. Defaults to None.
        """
        self.prompt = prompt
        self.llm = llm 
        self.tools = tools
        self.memory = memory
        self._create_agent_executor()

    @property
    def prompt(self):
        """
        str: The initial prompt for the agent.
        """
        print('prompt getter')
        return self._prompt

    @prompt.setter
    def prompt(self, value):
        """
        Sets the initial prompt for the agent.

        Args:
            value (str): The initial prompt for the agent.
        """
        if value is not None:
            self._prompt = value
        else:
            from utils.prompt import prompt
            self._prompt = prompt
    
    @property
    def llm(self):
        """
        ChatOpenAI: The language model used by the agent.
        """
        return self._llm

    @llm.setter
    def llm(self, llm):
        """
        Sets the language model for the agent.

        Args:
            llm (ChatOpenAI): The language model to be used by the agent.
        """
        if llm:
            self._llm = llm
        else:
            self._llm = ChatOpenAI(model=OPEN_AI_MODEL, temperature=0)   
    
    @property
    def tools(self):
        """
        list: The list of tools used by the agent.
        """
        return self._tools

    @tools.setter
    def tools(self, tools):
        """
        Sets the list of tools for the agent.

        Args:
            tools (list): The list of tools to be used by the agent.
        """
        if tools:
            self._tools = tools
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
        ConversationBufferWindowMemory: The memory to store conversation history.
        """
        return self._memory

    @memory.setter
    def memory(self, memory):
        """
        Sets the memory for the agent.

        Args:
            memory (ConversationBufferWindowMemory): The memory to store conversation history.
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
 
    def __call__(self, input):
        """
        Invokes the agent with the given input.

        Args:
            input (str): The input for the agent.

        Returns:
            str: The response generated by the agent.
        """
        response = self._agent_executor.invoke({"input": input})
        return response

    @classmethod
    def run(cls,**kwargs):
        """
        Creates and runs an instance of the CustomOpenAIToolsAgent class.

        Args:
            **kwargs: Additional keyword arguments to be passed to the constructor.

        Returns:
            CustomOpenAIToolsAgent: An instance of the CustomOpenAIToolsAgent class.
        """
        return cls(**kwargs)





# tools = [
#     create_retriever_tool(
#     retriever,
#     "technical_troubleshooting_questions",
#     prompt_language()['description_technical_troubleshooting'],
# ), 
# Tool(
#     name='custom_university_web_search',
#     func=SearchUniWeb.run(SERVICE),
#     description=prompt_language()['description_university_web_search'],
#     handle_tool_errors=True
# ),

# ]



"""
TODO 
ConversationBufferMemory stores every message sent by the agent and the user (this is not optimal)
we should store only the messages that are relevant to the conversation --> ConversationSummaryMemory. The downside of this 
approach is that it uses an LLM to summarize the conversation which can be more expensive (when using the OpenAI API).
A solution could be to provide a local model for the summarization. 
ConversationBufferWindowMemory --> this allows to define a K parameter, where K is the number of interactions to remember.
the thing is that a small K could lead to the agent not being able to remember the context of the conversation.
"""



#memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)



# Construct the OpenAI Tools agent
# agent = create_openai_tools_agent(llm, tools, prompt)

# TODO handle errors, specially when the characters exceed the limit allowed by the API


# agent_executor = AgentExecutor(agent=agent,
#                                tools=tools,
#                                verbose=True,
#                                memory=memory,
#                                handle_parsing_errors=True,
#                                max_execution_time=20, # Agent stops after 20 seconds
#                                )
# TODO to solve the character limit override the invoke method of the Chain class form which




if __name__ == "__main__":

    from langchain.callbacks import get_openai_callback


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

