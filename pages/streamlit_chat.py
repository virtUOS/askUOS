# run---> streamlit run streamlit_chat.py


import time
import streamlit as st
from streamlit import session_state
from src.config.core_config import settings
from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from src.chatbot.tools.utils.tool_helpers import visited_links
from src.chatbot_log.chatbot_logger import logger
from pages.utils import initialize_session_sate
from streamlit_feedback import streamlit_feedback

# create an instance of the agent executor
# TODO every time the users interacts with the chatbot, all the script  re-runS. This is not efficient. CACHE THE AGENT EXECUTOR??? (solved singltone pattern)
# TODO The id of the agent executor object is different every time the script runs. This is not efficient. CACHE THE AGENT EXECUTOR???
# TODO shall I cache this object and only recreate it when the input changes? the only thing that changes is the language (prompt)


initialize_session_sate()


greeting_message = session_state["_"]("How can I help you?")


agent_executor = CampusManagementOpenAIToolsAgent.run()

# App title
st.set_page_config(
    page_title="Ask.UOS",
    page_icon="app/static/Icon-chatbot.png",
    layout="centered",
    initial_sidebar_state="collapsed",
)


with open("./pages/static/style.css") as css:
    st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)


if session_state.get("show_warning", True):
    st.warning(
        session_state["_"](
            "The responses from the chat assistant may be incorrect - therefore, please verify the answers for their correctness."
        )
    )
    if st.button(session_state["_"]("I understand")):
        session_state["show_warning"] = False
        st.rerun()


st.title("Ask.UOS")

# Store LLM generated responses
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "avatar": "./static/Icon-chatbot.svg",
            "content": greeting_message,
        }
    ]

# Display chat messages
for message in st.session_state["messages"]:
    with st.chat_message(message["role"], avatar=message["avatar"]):
        st.write(message["content"])

# User-provided prompt
if prompt := st.chat_input(placeholder=session_state["_"]("Message")):
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "avatar": "./static/Icon-User.svg"}
    )
    with st.chat_message("user", avatar="./static/Icon-User.svg"):
        st.write(prompt)


if session_state.user_feedback:
    feedback = {
        "user_query": session_state.user_query,
        "response": session_state.messages[-1]["content"],
        "time_taken": session_state.time_taken,
        "rate": session_state.user_feedback["score"],
    }
    session_state.user_feedback = None
    logger.info(f"Feedback= {feedback}")


# Generate a new response if last message is not from assistant
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar="./static/Icon-chatbot.svg"):
        with st.spinner(session_state["_"]("Generating response...")):

            logger.info(f"User's query: {prompt}")
            # start time
            start_time = time.time()
            settings.time_request_sent = start_time

            response = agent_executor(prompt)

            end_time = time.time()
            time_taken = end_time - start_time
            session_state["time_taken"] = time_taken
            logger.info(
                f"Time taken to serve whole answer to the user: {time_taken} seconds"
            )

            # TODO if pdf is too long to display, provide a download link
            # check if the response contains a PDF file

            if visited_links():
                with st.expander("Sources"):
                    for link in visited_links():
                        st.write("- " + link)
                visited_links.clear()

        st.session_state.user_query = prompt
        feedback = streamlit_feedback(
            feedback_type="faces",
            key="user_feedback",
            # optional_text_label="[Optional] Please provide an explanation",
        )

    message = {
        "role": "assistant",
        "content": response["output"],
        "avatar": "./static/Icon-chatbot.svg",
    }
    st.session_state.messages.append(message)
