# run---> streamlit run streamlit_chat.py


import streamlit as st
# from retrieval_agent import agent
from agent_openai_tools import agent_executor

# Define the prompt text based on the selected language
start_message = "How may I help you?"

if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == 'Deutsch':
        start_message = "Wie kann ich Ihnen helfen?"

# App title
st.set_page_config(page_title="🤗💬 Campus Management Chatbot", page_icon="🤖", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown(
    """
<style>
    [data-testid="collapsedControl"] {
        display: none
    }
</style>
""",
    unsafe_allow_html=True,
)
# sidebar (include authentication backend here)

st.title('🤗💬 Campus Management')

# Store LLM generated responses
if "messages" not in st.session_state:
    st.session_state['messages'] = [{"role": "assistant", "content": start_message}]

# Display chat messages
for message in st.session_state['messages']:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# User-provided prompt
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

# Generate a new response if last message is not from assistant
# USING THE RETRIEVAL AGENT
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = agent_executor.invoke({"input": prompt})
            # response = agent.invoke({"input": prompt})

            # response = agent.invoke({"input": prompt}, config={"configurable": {"session_id": "<message_history>"}},)
            # response = agent.run({"input": prompt})

            st.write(response["output"])
            # st.write(response)
    message = {"role": "assistant", "content": response["output"]}
    st.session_state.messages.append(message)

# Generate a new response if last message is not from assistant

# USING THE CHAIN
# if st.session_state.messages[-1]["role"] != "assistant":
#     with st.chat_message("assistant"):
#         with st.spinner("Thinking..."):
#             response = GetAnswer.predict(prompt)
#             st.write(response)
#     message = {"role": "assistant", "content": response}
#     st.session_state.messages.append(message)
