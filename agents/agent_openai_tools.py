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
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain.agents.format_scratchpad.openai_tools import (
    format_to_openai_tool_messages,
)
from langchain.agents import load_tools
from tools.uni_application_tool import application_instructions
import streamlit as st
from utils.prompt import get_prompt
from json import JSONDecodeError
from langchain_core.exceptions import OutputParserException


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

    output: str = Field(description="The final answer to respond to the user")
    sources: List[str] = Field(
        description="The sources used to find the answer, it should be a list of URLs. Only include this field if the answer is based on external sources obtain from the web"
    )


def parse(message):

    # If no function was invoked, return to user
    if "function_call" not in message.additional_kwargs:
        return AgentFinish(return_values={"output": message.content}, log=message.content)

    # Parse out the function call
    function_call = message.additional_kwargs["function_call"]
    function_name = function_call["name"]
    
    try:
    
        # additional_kwargs= {'function_call': {'arguments': '{{"output":""..."", "sources"}, 'name': '...'}' } }
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
                ),
                
                Tool (
                    
                    name='application_instructions',
                    func=application_instructions,
                    description="""  
                    
                    Useful when users want to apply to the university and need a guide (step by step) on how to do it. DO NOT provide all the instructions at once, provide them step by step and use a conversational tone to guide the user through the process. for example,
                    provide the first instruction and wait for the user to confirm that they have completed it before providing the next instruction. Use of the chat_history in order to provide a more personalized experience to the user.
                    If the user needs more information, the agent can use the other tools to provide more information about the application process, for example, use the 'custom_university_web_search' tool to find more information about the application process or 
                    the 'technical_troubleshooting_questions' tool to help the user with any technical issues they might have during the application process. 
                   
                    """,  
                    handle_tool_errors=True
                    
                )
                
                
                ]
    
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
            #self._memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)
  
    def _create_agent_executor(self):
        """
        Creates the agent executor for the agent.
        """
        agent = create_openai_tools_agent(self._llm, self._tools, self._prompt)

        
        llm_with_tools = self._llm.bind_functions([self._tools[0],self._tools[1], self._tools[2],load_tools(["human"])[0], Response])

            
        agent = (   # prompt input_variables=['input', 'chat_history', 'agent_scratchpad']
                    {
                        "input": lambda x: x["input"],
                        "chat_history": lambda x: x["chat_history"],
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
                               return_intermediate_steps=True,
                               verbose=True,
                               memory=self._memory,
                               handle_parsing_errors=True,
                               max_execution_time=30, # Agent stops after 20 seconds
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
        
    
    
    
    
    # from langchain.callbacks import get_openai_callback
    # from utils.prompt import prompt


    # def count_tokens(agent_ex, input):
    #         with get_openai_callback() as cb:
    #             result = agent_ex.invoke({'input':input})
    #             print(f'Spent a total of {cb.total_tokens} tokens')

    #         return result

    

    # response = agent_executor({"input": 'Richtlinie der Universität Osnabrück für die Vergabe von Deutschlandstipendien'}) # should return the pdf
    # response = agent_executor({"input": 'Abschlussnote Psychologiestudium Osnabrueck'})
    # # response = count_tokens(agent_executor, 'muss ich das Einverständnis meiner Eltern haben?')
    # response =agent_executor({"input": 'where is the university'})
    # response = agent_executor({"input": 'what is the application process'})
    # response = agent_executor({"input": 'what is the application deadline'})
    # response = agent_executor({"input": 'how much does it cost?'})
    print()

