from langchain.chains import LLMChain
from langchain.chains import RetrievalQA, ConversationalRetrievalChain, StuffDocumentsChain
from langchain_community.llms import Ollama
import gradio as gr
from langchain_core.messages import SystemMessage

from db.vector_store import retriever
from langchain.prompts.prompt import PromptTemplate
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.memory import ConversationSummaryBufferMemory, ConversationBufferMemory
from langchain_community.chat_models import ChatOllama
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
)

# LLM
# model
chat_model = ChatOllama(
    model="llama2:13b-chat",
)


memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)



template_messages = [SystemMessage(content="""You work for a german university as an advisor who supports prospect students with their application process.
                           Provide answers in German if the student asks in German, and in English if the student asks in English.
                             The AI is talkative and provides lots of specific details from its context.
                          If the AI does not know the answer to a question, it truthfully says it does not know.
               """),
                     MessagesPlaceholder(variable_name='chat_history'),
                     HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['question'], template='{question}'))]



prompt_template = ChatPromptTemplate.from_messages(template_messages)

# page_content --> this refers to the chunks generated by the CharacterTextSplitter.
# there are as many page_content as there are chunks
# DEFAULT_DOCUMENT_PROMPT = PromptTemplate.from_template("{page_content}")
# this prompt is used to format the documents
document_prompt = PromptTemplate(
    input_variables=["page_content"],
    template="{page_content}" # refers to the input variable page_content
)

# The variable name in the llm_chain to put the documents in.
document_variable_name = "context"

combine_prompt = PromptTemplate.from_template(
    "Summarize this information: {context}"
)
# todo here the LLM is asked to summarize the documents
llm_combine_chain = LLMChain(llm=chat_model)

combine_docs_chain = StuffDocumentsChain(
    llm_chain=llm_combine_chain,
    document_prompt=document_prompt,
    document_variable_name=document_variable_name
)


# this chain generates a new question (standalone question) based on the chat history and the question.
# the retriever uses this standalone question to retrieve documents and they are combined using the combine_docs_chain
# the new question can be accessed through the variable `answer`
question_generator_chain = LLMChain(llm=chat_model, prompt=prompt_template)

chain = ConversationalRetrievalChain(
    memory = memory,
    combine_docs_chain=combine_docs_chain, # The chain used to combine any retrieved documents.
    retriever=retriever,
    question_generator=question_generator_chain,
)



def predict(message: str, history: str):
    response = chain.invoke({"question": message})
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