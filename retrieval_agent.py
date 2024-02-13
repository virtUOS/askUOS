from langchain.tools.retriever import create_retriever_tool
from vector_store import retriever
from langchain.prompts.prompt import PromptTemplate
from langchain_core.prompts import SystemMessagePromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent

import dotenv
dotenv.load_dotenv()

chat_model = ChatOpenAI(
    model="gpt-3.5-turbo-1106",
    temperature=0.3,
)


tool = create_retriever_tool(
    retriever,
    "search_university_application_information",
    "Searches and returns excerpts about the university of Osnabrueck application process.",
)
tools = [tool]


template_messages = [SystemMessagePromptTemplate(prompt=PromptTemplate(input_variables=['context', 'chat_history'],
                                                                       template="""You work for a german university as an advisor who 
                                                                       supports prospect students with their application process.
                           Provide answers in German if the student asks in German. Provides answers in in English if the student asks in English.
                             Do not greet the user. Avoid using greetings. The AI is talkative and provides specific details from its context. It include links, if these are provided in the context.  
                          If the AI does not know the answer to a question, it truthfully says it does not know. If the user asks question which are not about University studies in Germany, the AI will say it does not know.
                Answer any user questions based solely on the context and chat history provided below. If the context doesn't contain any relevant information to the question, don't make something up and just say "I don't know.
             """)),
                     MessagesPlaceholder(variable_name='chat_history', optional=True),
                     HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['input'], template='{input}')),
                     MessagesPlaceholder(variable_name='agent_scratchpad')]



prompt = ChatPromptTemplate.from_messages(template_messages)


agent = create_openai_tools_agent(chat_model, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)

# result = agent_executor.invoke({"input": "hi, im bob"})
print()
