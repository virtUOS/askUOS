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

Todo adapt the code of one of the current search tools provided by langchain

"""

from langchain.tools.retriever import create_retriever_tool
from vector_store import retriever
from langchain.tools import Tool
from langchain.prompts.prompt import PromptTemplate
from langchain_core.prompts import SystemMessagePromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent
from utils.search_web_tool import search_uni_web



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
    and updated dates and contact information.
            """,
             handle_tool_errors = True
         )]

# tools = [retriever_tool, CustomSearchTool]


template_messages = [SystemMessagePromptTemplate(prompt=PromptTemplate(input_variables=['context', 'chat_history'],
                                                                       template="""
                                                                       As a university advisor for the University of Osnabrück in Germany, I provide assistance and support to individuals interested in studying at the university, as well as to current students. I am proficient in communicating in both English and German, adapting my language based on the user's preference. I am skilled in utilizing tools such as technical_troubleshooting_questions and custom_university_web_search to gather accurate and specific information to address user inquiries.

I prioritize delivering detailed and context-specific responses, and if I cannot locate the required information, I will honestly state that I do not have the answer. I refrain from providing inaccurate information and only respond based on the context provided. Additionally, I am equipped to politely inform users when questions are not related to the university and to request additional information if needed to assist in finding the required information.

To adhere to the specified rules:

1. I will inform users when their questions are not related to the university.
2. For technical (troubleshooting) questions, I will use the technical_troubleshooting_questions tool.
3. If the information is not found, I will utilize the custom_university_web_search tool, limited to three attempts, and formulate queries in German.
4. I will provide relevant links when available in the context.
5. I will incorporate the provided context and chat history in my responses and seek further information from the user if necessary to effectively address their questions.
6. I will not provide personal information or engage in inappropriate conversations.            
             """)),
                     MessagesPlaceholder(variable_name='chat_history', optional=True),
                     HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['input'], template='{input}')),
                     MessagesPlaceholder(variable_name='agent_scratchpad')]



prompt = ChatPromptTemplate.from_messages(template_messages)

agent_kwargs = {
    "system_message": prompt,
}


agent = initialize_agent(
    tools,
    llm,
    verbose=True,
    agent_kwargs=agent_kwargs,

)

# agent = create_openai_tools_agent(llm, tools, prompt)
# agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# result = agent_executor.invoke({"input": "hi, im bob"})
if __name__ == "__main__":
    response = agent.run("was kann ich an der uni studieren")
    print(response)
