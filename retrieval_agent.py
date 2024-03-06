""""
This agent should first see if there's enough information in the db to answer the questions.
Otherwise the agent searches the university website for information and uses the retrieved information to
answer the question.

(free search tools
 https://python.langchain.com/docs/integrations/tools/ddg
 https://python.langchain.com/docs/integrations/tools/search_tools --> you need to set up your own search engine

 )
workflow
if the question is about troubleshooting the agent should look for information in the DB
if the question is about the university, the agent should look for information on the website
Before the agent looks for information in the website, the agent needs to generate a query

Todo the agent should try the web search three tines with different queries. If the agent can't find the information should ask the user for more information

"""

from langchain.agents import AgentType
from langchain.tools.retriever import create_retriever_tool
from vector_store import retriever
from langchain.tools import Tool
from utils.prompt import prompt
from langchain.prompts.chat import MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent
from utils.search_web_tool import search_uni_web
from langchain.memory import ConversationBufferMemory

import dotenv
dotenv.load_dotenv()

llm = ChatOpenAI(
    model="gpt-3.5-turbo-1106",
    temperature=0.3,

)


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



agent_kwargs = {
    "system_message": prompt,
"extra_prompt_messages": [MessagesPlaceholder(variable_name="chat_history")],
}


agent = initialize_agent(
    tools,
    llm,
    verbose=True,
agent=AgentType.OPENAI_FUNCTIONS,
    agent_kwargs=agent_kwargs,
    memory=memory,
    handle_parsing_errors=True,

)


if __name__ == "__main__":
    response = agent.run("was kann ich an der uni studieren")
    print(response)
