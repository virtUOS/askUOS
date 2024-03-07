from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools.retriever import create_retriever_tool
from vector_store import retriever
from langchain.tools import Tool
from utils.prompt import prompt
from langchain_openai import ChatOpenAI
from utils.search_web_tool import search_uni_web
from langchain.memory import ConversationBufferMemory


llm = ChatOpenAI(model="gpt-3.5-turbo-1106", temperature=0)



retriever_tool = create_retriever_tool(
    retriever,
    "technical_troubleshooting_questions",
    "Use this tool to answer technical questions about the application process. This tool is also useful to help the user when they encounter technical problems (troubleshooting) "
    "For example, questions about how to use the software"
    "through which the application is submitted.",
)
tools = [retriever_tool,

         Tool(
             name= 'custom_university_web_search',
            func= search_uni_web,
            description ="""
            useful for when you need to answer questions about the University of Osnabrück. For example questions about 
    the application process or studying at the university in general. This tool is also useful to access updated application dates
    and updated dates and contact information. To use this tool successfully, take into account the previous interactions with the user (chat history) and the context of the conversation.
            """,
             handle_tool_errors = True
         )]




memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Construct the OpenAI Tools agent
agent = create_openai_tools_agent(llm, tools, prompt)

agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)

