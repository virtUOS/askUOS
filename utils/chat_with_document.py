from langchain.chains import LLMChain
from langchain.chains import ConversationalRetrievalChain
import gradio as gr
from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
)
from langchain_community.llms import Ollama
from vector_store import retriever


# todo: change to llama2 chat model
# LLM
llm = Ollama(model="llama2")

# Prompt
prompt = ChatPromptTemplate(
    messages=[
        SystemMessagePromptTemplate.from_template(
            "You are a nice chatbot having a conversation with a human."
        ),
        # The `variable_name` here is what must align with memory
        MessagesPlaceholder(variable_name="chat_history"),
        HumanMessagePromptTemplate.from_template("{question}"),
    ]
)

# Notice that we `return_messages=True` to fit into the MessagesPlaceholder
# Notice that `"chat_history"` aligns with the MessagesPlaceholder name
memory =  ConversationSummaryMemory(
    llm=llm, memory_key="chat_history", return_messages=True
)


qa = ConversationalRetrievalChain.from_llm(llm, retriever=retriever, memory=memory)

q = qa('can apply with a hotmail email?')

print()

def predict(message: str, history: str):

    response = qa(message)
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