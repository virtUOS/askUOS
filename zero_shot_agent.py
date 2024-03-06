"""
ZeroShotAgent with Memory and Retrieval Tools Example

"""


from langchain.agents import AgentExecutor, Tool, ZeroShotAgent,  create_react_agent
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain_openai import OpenAI
from langchain.agents import AgentType
from utils.search_web_tool import search_uni_web
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
from langchain.agents import initialize_agent
import dotenv
dotenv.load_dotenv()

# llm = OpenAI(
#     model="gpt-3.5-turbo-1106",
#     temperature=0.3,
#
# )

retriever_tool = create_retriever_tool(
    retriever,
    "technical_troubleshooting_questions",
    "Use this tool to answer technical questions about the application process. This tool is also useful to help the user when they encounter technical problems (troubleshooting) "
    "For example, questions about how to use the software"
    "through which the application is submitted.",
)
tools = [retriever_tool,

         Tool(
             name='custom_university_web_search',
             func=search_uni_web,
             description="""
            useful for when you need to answer questions about the University of Osnabrueck. For example questions about 
    the application process or studying at the university in general. This tool is also useful to access updated application dates
    and updated dates and contact information. To use this tool successfully, take into account the previous interactions with the user (chat history) and the context of the conversation.
            """,
             handle_tool_errors=True
         )]




prefix = """ Have a conversation with a human. You work as a university advisor for the University of Osnabrueck in Germany, you provide assistance and support to individuals interested in studying at the university, as well as to current students.
             You are proficient in communicating in both English and German, adapting your language based on the user's preference.
            Prioritize delivering detailed and context-specific responses, and if you cannot locate the required information, you will honestly state that you do not have the answer. Refrain from providing inaccurate information and only respond based on the context provided.
            Additionally. You have access to the following tools:"""
suffix = """
Please make sure you complete the objective above with the following rules:
1. Inform users when their questions are not related to the university.
2. If the user asks  technical (troubleshooting) questions, use the technical_troubleshooting_questions tool to answer the question. You are allowed to use the technical_troubleshooting_questions tool only 3 times in this process.
3. Utilize the custom_university_web_search tool to answer questions about applying and studying at the University. You are allowed to use the search tool custom_university_web_search only 3 times in this process.
4. Provide a conversational answer with a hyperlink to the documentation (if there are any).
5. Incorporate the provided context and chat history (provided below) in the responses and seek further information from the user if necessary to effectively address their questions.
6. Do not provide personal information or engage in inappropriate conversations.
7. You can ask questions to the user to gather more information if necessary.
8. You can use the chat history to provide context-specific responses.

{chat_history}
Question: {input}
{agent_scratchpad}"""



prompt = ZeroShotAgent.create_prompt(
    tools,
    prefix=prefix,
    suffix=suffix,
    input_variables=["input", "chat_history", "agent_scratchpad"],
)



memory = ConversationBufferMemory(memory_key="chat_history", k=5)



llm_chain = LLMChain(llm=OpenAI(temperature=0), prompt=prompt)

agent = ZeroShotAgent(llm_chain=llm_chain, tools=tools, verbose=True)
agent_chain = AgentExecutor.from_agent_and_tools(
    agent=agent, tools=tools, verbose=True, memory=memory, handle_parsing_errors=True
)

#agent_chain.run(input="How many people live in canada?")
print()