from langchain.chains import LLMChain
from langchain.chains import RetrievalQA, ConversationalRetrievalChain, StuffDocumentsChain
from langchain_community.llms import Ollama
import gradio as gr
from vector_store import retriever
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
llm = Ollama(model="llama2")




# Template using jinja2 syntax
# template = """
# <s>[INST] <<SYS>>
# You work for a german university as an advisor who supports prospect students with their application process.
# Provide answers in German if the student asks in German, and in English if the student asks in English.
# The AI is talkative and provides lots of specific details from its context.
# If the AI does not know the answer to a question, it truthfully says it does not know.
# Please be concise.
# <</SYS>>
#
# Current conversation:
# {{ chat_history }}
#
# {% if chat_history %}
#     <s>[INST] Human: {{ question }} [/INST] AI: </s>
# {% else %}
#     Human: {{ question }} [/INST] AI: </s>
# {% endif %}
# """
#
# prompt = PromptTemplate(
#     input_variables=["chat_history", "question"],
#     template=template,
#     template_format="jinja2"
# )

document_prompt = PromptTemplate(
    input_variables=["page_content"],
    template="{page_content}"
)
document_variable_name = "context"
# The prompt here should take as an input variable the
# `document_variable_name`
prompt = PromptTemplate.from_template(
    "This is useful content to expand your built-in knowledge: {context}"
)
llm_chain = LLMChain(llm=llm, prompt=prompt)
combine_docs_chain = StuffDocumentsChain(
    llm_chain=llm_chain,
    document_prompt=document_prompt,
    document_variable_name=document_variable_name
)

# todo you need to inject the context into the prompt  add someting like: "This is useful content to expand your built-in knowledge: {context}"

template = (
    "You work for a german university as an advisor who supports prospect students with their application process. Provide answers in German if the student asks in German, and in English if the student asks in English."
    "Do not invent information, if you cannot provide a factual answer, say you do not know the answer."
    "Chat History: {chat_history}"
    "question: {question}"
)
prompt = PromptTemplate.from_template(template)
question_generator_chain = LLMChain(llm=llm, prompt=prompt)
chain = ConversationalRetrievalChain(
    combine_docs_chain=combine_docs_chain,
    retriever=retriever,
    question_generator=question_generator_chain,
)

#chain.invoke({'question': "can i use a hotmal email to register at the uni website?", 'chat_history':''})

# qa = ConversationalRetrievalChain.from_llm(
#     llm=llm,
#     # memory=ConversationBufferMemory(),
#     condense_question_prompt=prompt,
#     chain_type="map_reduce",
#     return_source_documents=False,
#     retriever=retriever,
#     verbose=False,
# )

#qa('can i use hotmail for the registration on the uni website?')
# Initialize the conversation chain
# conversation = ConversationChain(
#     llm=llm,
#     memory=ConversationBufferMemory(),
#     prompt=prompt,
#     verbose=False,
#
# )

# conversation = RetrievalQA(
#     llm=llm,
#     memory=ConversationBufferMemory(),
#     prompt=prompt,
#     verbose=False,
#     chain_type="map_reduce",
#     retriever=retriever,
# )


print()
# Start the conversation
def predict(message: str, history: str):
    response = conversation.predict(input=message)

    return response


# Create a RetrievalQA chain to answer questions that incorporate documents into the prompt






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