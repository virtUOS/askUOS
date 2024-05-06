from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools.retriever import create_retriever_tool
from vector_store import retriever
from langchain.tools import Tool
from utils.prompt import prompt
from langchain_openai import ChatOpenAI
from utils.search_web_tool import  SearchUniWeb
from langchain.memory import ConversationBufferMemory
import streamlit as st
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from utils.language import prompt_language
from settings import SERVICE




# TODO change model to gpt-3.5-turbo
llm = ChatOpenAI(model="gpt-3.5-turbo-1106", temperature=0)

# create tools

# retriever_tool = create_retriever_tool(
#     retriever,
#     "technical_troubleshooting_questions",
#     prompt_language()['description_technical_troubleshooting'],
# )

# search_uni_web_tool = Tool(
#     name='custom_university_web_search',
#     func=SearchUniWeb.run(SERVICE),
#     description=prompt_language()['description_university_web_search'],
#     handle_tool_errors=True
# )


tools = [
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

# tools = [retriever_tool, search_uni_web_tool]



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

memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)



# Construct the OpenAI Tools agent
agent = create_openai_tools_agent(llm, tools, prompt)

# TODO handle errors, specially when the characters exceed the limit allowed by the API


agent_executor = AgentExecutor(agent=agent,
                               tools=tools,
                               verbose=True,
                               memory=memory,
                               handle_parsing_errors=True,
                               max_execution_time=20, # Agent stops after 20 seconds
                               )
# todo, to solve the character limit override the invoke method of the Chain class form which
# the AgentExecutor inherits from

if __name__ == "__main__":

    from langchain.callbacks import get_openai_callback


    def count_tokens(agent_ex, input):
        with get_openai_callback() as cb:
            result = agent_ex.invoke({'input':input})
            print(f'Spent a total of {cb.total_tokens} tokens')

        return result
    
    response = agent_executor.invoke({"input": 'Richtlinie der Universität Osnabrück für die Vergabe von Deutschlandstipendien'}) # should return the pdf
    response = agent_executor.invoke({"input": 'Abschlussnote Psychologiestudium Osnabrueck'})
    response = count_tokens(agent_executor, 'muss ich das Einverständnis meiner Eltern haben?')
    response =agent_executor.invoke({"input": 'where is the university'})
    response = agent_executor.invoke({"input": 'what is the application process'})
    response = agent_executor.invoke({"input": 'what is the application deadline'})
    response = agent_executor.invoke({"input": 'how much does it cost?'})
    print()

