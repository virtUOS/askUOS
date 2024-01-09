from langchain.chains import LLMChain
from langchain_community.llms import Ollama
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
# chat_model = ChatOllama()

# Prompt
prompt = ChatPromptTemplate(
    messages=[
        SystemMessagePromptTemplate.from_template(
            "You work for a german university as an advisor who supports prospect students with their application process."
        ),
        # The `variable_name` here is what must align with memory
        MessagesPlaceholder(variable_name="chat_history"),
        HumanMessagePromptTemplate.from_template("{question}"),
    ]
)

# Notice that we `return_messages=True` to fit into the MessagesPlaceholder
# Notice that `"chat_history"` aligns with the MessagesPlaceholder name
memory = ConversationSummaryBufferMemory(llm=llm, max_token_limit=10, memory_key="chat_history", return_messages=True)
conversation = LLMChain(llm=llm, prompt=prompt, verbose=True, memory=memory)

# Notice that we just pass in the `question` variables - `chat_history` gets populated by memory
# conversation({"question": "what about health insurance?"})

# Start the conversation
def predict(message: str, chat_history: str):
    print (message)
    response = conversation.predict(input={"question":message})

    return response



import gradio as gr

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