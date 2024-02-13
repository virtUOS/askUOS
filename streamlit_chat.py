# run---> streamlit run streamlit_chat.py


import streamlit as st
from retrieval_agent import agent_executor
# App title
st.set_page_config(page_title="🤗💬 Campus Management Chatbot", page_icon="🤖", layout="centered", initial_sidebar_state="auto")

# sidebar (include authentication backend here)
with st.sidebar:
    st.title('🤗💬 Campus Management')


# Store LLM generated responses
if "messages" not in st.session_state.keys():
    st.session_state.messages = [{"role": "assistant", "content": "How may I help you?"}]


# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])




# User-provided prompt
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)


# Generate a new response if last message is not from assistant
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = agent_executor.invoke({"input": prompt})
            st.write(response["output"])
    message = {"role": "assistant", "content": response["output"]}
    st.session_state.messages.append(message)
