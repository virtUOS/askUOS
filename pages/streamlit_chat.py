# run---> streamlit run streamlit_chat.py


import streamlit as st
from chatbot_log.chatbot_logger import logger
import time
from streamlit import session_state
from agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from utils.prompt import get_prompt


# create an instance of the agent executor
# TODO every time the users interacts with the chatbot, all the script  re-runS. This is not efficient. CACHE THE AGENT EXECUTOR???
# TODO The id of the agent executor object is different every time the script runs. This is not efficient. CACHE THE AGENT EXECUTOR???
# TODO shall I cache this object and only recreate it when the input changes? the only thing that changes is the language (prompt)



start_message = "How may I help you?"
if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == 'Deutsch':
        start_message = "Wie kann ich Ihnen helfen?"
        from utils.prompt_text import prompt_text_deutsch as prompt_text
    else:
        from utils.prompt_text import prompt_text_english as prompt_text
else:

    from utils.prompt_text import prompt_text_english as prompt_text


agent_executor = CampusManagementOpenAIToolsAgent.run(prompt=get_prompt(prompt_text))

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

def get_feedback(user_query,response,time_taken,rate):
    feedback = {"user_query": user_query, "response": response, 'time_taken':time_taken,"rate": rate}
    logger.info(f"Feedback= {feedback}")


# Generate a new response if last message is not from assistant
# USING THE RETRIEVAL AGENT
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
           
            logger.info(f"User's query: {prompt}")
            # start time
            start_time = time.time()
            # response = agent_executor({"input": prompt})
            response = agent_executor(prompt)
            # response = agent.invoke({"input": prompt})
            # end time
            end_time = time.time()
            time_taken = end_time - start_time
            logger.info(f"Time taken to generate a response: {time_taken} seconds")
            # response = agent.invoke({"input": prompt}, config={"configurable": {"session_id": "<message_history>"}},)
            # response = agent.run({"input": prompt})

            st.write(response["output"])
            # st.write(response)

    col1,col2,col3,col4 = st.columns([3,3,0.5,0.5])
    with col3:
        st.button(":thumbsup:", on_click=get_feedback, 
                  args=[prompt,response["output"],time_taken,"like"],
                  help="Click here if you like the response")
            
    with col4:
        st.button(":thumbsdown:", on_click=get_feedback, 
                  args=[prompt,response["output"],time_taken,"dislike"], 
                  help="Click here if you dislike the response")
           


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
