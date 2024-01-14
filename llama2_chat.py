from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain_experimental.chat_models import Llama2Chat
from langchain_community.llms import Ollama
from langchain.schema import HumanMessage
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

# model
chat_model = ChatOllama(
    model="llama2:13b-chat",
    callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
)

template_messages = [
    SystemMessage(content="You are a helpful assistant."),
    MessagesPlaceholder(variable_name="chat_history"),
    HumanMessagePromptTemplate.from_template("{text}"),
]
prompt_template = ChatPromptTemplate.from_messages(template_messages)



memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
chain = LLMChain(llm=chat_model, prompt=prompt_template, memory=memory)


# messages = [HumanMessage(content="Tell me two things about the history of AI")]
#
#
# result = chat_model(messages)


print()


def predict(message: str, history: str):

    response = chat_model([HumanMessage(content=message)])
    return response.content


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