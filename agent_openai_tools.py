from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools.retriever import create_retriever_tool
from vector_store import retriever
from langchain.tools import Tool
from utils.prompt import prompt
from langchain_openai import ChatOpenAI
from utils.search_web_tool import search_uni_web
from langchain.memory import ConversationBufferMemory
import streamlit as st

# Define the prompt text based on the selected language

if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == 'English':
        from utils.prompt_text import prompt_text_english as prompt_text
    elif st.session_state["selected_language"] == 'Deutsch':
        from utils.prompt_text import prompt_text_deutsch as prompt_text
else:
    from utils.prompt_text import prompt_text_english as prompt_text


llm = ChatOpenAI(model="gpt-3.5-turbo-1106", temperature=0)

retriever_tool = create_retriever_tool(
    retriever,
    "technical_troubleshooting_questions",
    prompt_text['description_technical_troubleshooting'],
)

print(f"------------------------------retriever_tool description: {prompt_text['description_technical_troubleshooting']}")



tools = [retriever_tool,

         Tool(
             name='custom_university_web_search',
             func=search_uni_web,
             description=prompt_text['description_university_web_search'],
             handle_tool_errors=True
         )]


print(f"------------------------------description_university_web_search description: {prompt_text['description_university_web_search']}")

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Construct the OpenAI Tools agent
agent = create_openai_tools_agent(llm, tools, prompt)

# todo hangle errors, specially when the characters exceed the limit allowed by the API
# Agent stops after 15 seconds
agent_executor = AgentExecutor(agent=agent,
                               tools=tools,
                               verbose=True,
                               memory=memory,
                               handle_parsing_errors=True,

                               max_execution_time=15,)


