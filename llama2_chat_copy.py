from langchain.chains import LLMChain, StuffDocumentsChain, ConversationalRetrievalChain
from langchain_core.prompts import SystemMessagePromptTemplate

from vector_store import retriever
from langchain.prompts.prompt import PromptTemplate
from langchain.memory import ConversationBufferMemory
from langchain_experimental.chat_models import Llama2Chat
from langchain_community.llms import Ollama
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
import gradio as gr
from langchain.schema import SystemMessage

from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.chat_models import ChatOllama

from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain import hub

# model
chat_model = ChatOllama(
    model="llama2:13b-chat",
)

template_messages = [SystemMessagePromptTemplate(prompt=PromptTemplate(input_variables=['context'],
                                                                           template="""You work as an advisor for Osnabrueck University (Germany)  who supports prospect students with their application process.
                           Provide answers in German.
                             The AI is talkative and provides lots of specific details from its context.
                          If the AI does not know the answer to a question, it truthfully says it does not know.
                Answer any use questions based solely on the context below:\n\n<context>\n{context}\n</context>""")),
                     MessagesPlaceholder(variable_name='chat_history', optional=True),
                     HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['input'], template='{input}'))]



prompt_template = ChatPromptTemplate.from_messages(template_messages)

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# prompt_template2 = hub.pull("langchain-ai/retrieval-qa-chat")

retriever = retriever


combine_docs_chain = create_stuff_documents_chain(
    chat_model, prompt_template
)
retrieval_chain = create_retrieval_chain(retriever, combine_docs_chain)


# a = retrieval_chain.invoke({"input": "Name three study programs at the University"})
#
#
# b = retrieval_chain.invoke({"input": "Tell me more about the second program"})

print()



def predict(message: str, history: str):
    response = retrieval_chain.invoke({"input": message})
    return response['answer']


# Set up the user interface
interface = gr.ChatInterface(
    clear_btn=None,
    fn=predict,
    retry_btn=None,
    undo_btn=None,
)

# Launch the user interface
interface.launch(
    height=600,
    inline=True,
    share=True,
    width=800
)
