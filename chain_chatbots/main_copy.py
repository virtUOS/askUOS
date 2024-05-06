from langchain.chains import LLMChain
from langchain.chains import RetrievalQA, ConversationalRetrievalChain, StuffDocumentsChain
from langchain_community.llms import Ollama
import gradio as gr
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
llm = Ollama(model="llama2")

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)


# Template using jinja2 syntax
template = """
<s>[INST] <<SYS>>
You work for a german university as an advisor who supports prospect students with their application process.
Provide answers in German if the student asks in German, and in English if the student asks in English.
The AI is talkative and provides lots of specific details from its context.
If the AI does not know the answer to a question, it truthfully says it does not know.
Please be concise.
<</SYS>>

Current conversation:
{{ chat_history }}

{% if chat_history %}
    <s>[INST] Human: {{ question }} [/INST] AI: </s>
{% else %}
    Human: {{ question }} [/INST] AI: </s>
{% endif %}
"""

user_prompt = PromptTemplate(
    input_variables=["chat_history", "question"],
    template=template,
    template_format="jinja2"
)

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

# todo this prompt maybe is not needed, This context should be injected into the prompt below. This should only join the documents
# todo or all the combined documents are summerized and then injected into the prompt below using the ConversationalRetrievalChain
# this is the prompt that is used to combine the documents ??
combine_prompt = PromptTemplate.from_template(
    "Summarize this information: {context}"
)
# todo here the LLM is asked to summerize the documents
llm_combine_chain = LLMChain(llm=llm, prompt=combine_prompt)
# all documents joined  with `document_separator`
# todo does this return an embedding for all documents, and is this used by the retriever?
# todo or does the retriever pass the documents to the StuffDocumentsChain?
# ?? puts all documents into format the documents according to the document_prompt, puts documents into document_variable_name
# ?? executes the llm_chain to summerize the documents (as asked in the prompt)

combine_docs_chain = StuffDocumentsChain(
    llm_chain=llm_combine_chain,
    document_prompt=document_prompt,
    document_variable_name=document_variable_name
)

# todo you need to inject the context into the prompt  add someting like: "This is useful content to expand your built-in knowledge: {context}"

condense_question_template = (
                "Combine the chat history and follow up question into "
                "a standalone question. Chat History: {chat_history}"
                "Follow up question: {question}"
                "Now answer the newly generated question. Bear in mind the you work for a german university as an advisor who supports prospect students with their application process."
            )

# The prompt to use to condense the chat history and new question into a standalone question.
condense_question_prompt = PromptTemplate.from_template(condense_question_template)


# this chain generates a new question (standalone question) based on the chat history and the question.
# the retriever uses this standalone question to retrieve documents and they are combined using the combine_docs_chain
# the new question can be accessed through the variable `answer`
question_generator_chain = LLMChain(llm=llm, prompt=condense_question_prompt)
# chain_standalone_question_retrieve = ConversationalRetrievalChain(
#     memory = ConversationBufferMemory(),
#     combine_docs_chain=combine_docs_chain, # The chain used to combine any retrieved documents.
#     retriever=retriever,
#     question_generator=question_generator_chain,
# )


# this returns and answer with the variable name `answer` (the answer is the new question)???
qa = ConversationalRetrievalChain.from_llm(

    llm=llm,
    retriever=retriever,
    memory = memory,
    condense_question_prompt=condense_question_prompt,
    # combine_docs_chain_kwargs={
    #
    #     'prompt': combine_prompt,
    #     'document_variable_name': document_variable_name
    # }

)

# todo how can i pass the history to the chain?
"""
history = []
history.append(question, answer)
"""


# this new question along with the retrieved documents needs to be fed to the conversation chain to generate a response
#answer = qa({'question':'can i use hotmail?', 'chat_history':''})


#print(answer['answer'])


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
#     memory=ConversationBufferMemory(),
#     combine_documents_chain=combine_docs_chain,
#     verbose=False,
#     # chain_type="map_reduce",
#     retriever=retriever,
# )


# conversation = RetrievalQA.from_chain_type(
#     llm=llm,
#     memory=ConversationBufferMemory(),
#     chain_type="map_reduce", # tells how to combine the documents retrieved by the retriever
#     retriever=retriever,
#
# )

print()
# Start the conversation
# def predict(message: str, history: str):
#     response = qa.predict(input=message, chat_history=history)
#
#     return response

history_manual = []
def predict(message: str, history: str):

    response = qa({'question':message, 'chat_history':history_manual})
    history_manual.append((message,response['answer']))
    print(history)
    return response['answer']


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