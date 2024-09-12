# run---> streamlit run streamlit_chat.py


import time

import streamlit as st
from streamlit import session_state

from chatbot.agents.agent_openai_tools import (
    CampusManagementOpenAIToolsAgent,
)
from chatbot_log.chatbot_logger import logger
from chatbot.utils.pdf_reader import extract_pdf_with_timeout
from chatbot.utils.prompt import get_prompt

# create an instance of the agent executor
# TODO every time the users interacts with the chatbot, all the script  re-runS. This is not efficient. CACHE THE AGENT EXECUTOR??? (solved singltone pattern)
# TODO The id of the agent executor object is different every time the script runs. This is not efficient. CACHE THE AGENT EXECUTOR???
# TODO shall I cache this object and only recreate it when the input changes? the only thing that changes is the language (prompt)


start_message = "Wie kann ich Ihnen helfen?"
if "selected_language" in st.session_state:
    if st.session_state["selected_language"] == "English":
        start_message = "How can I help you?"


agent_executor = CampusManagementOpenAIToolsAgent.run()

# App title
st.set_page_config(
    page_title="🤗💬 Campus Management Chatbot",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)


if "show_warning" in st.session_state:
    if st.session_state["show_warning"] == True:
        st.warning(
            "The responses from the chat assistant may be incorrect - therefore, please verify the answers for their correctness."
        )
        if st.button("Ich verstehe"):
            st.session_state["show_warning"] = False
            st.rerun()
else:

    st.warning(
        "Die Ausgaben des Chat-Assistenten können fehlerhaft sein - überprüfen Sie die Antworten daher unbedingt auf ihre Korrektheit."
    )
    if st.button("Ich verstehe"):
        st.session_state["show_warning"] = False
        st.rerun()


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

st.title("🤗💬 Campus Management")

# Store LLM generated responses
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": start_message}]

# Display chat messages
for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# User-provided prompt
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)


def get_feedback(user_query, response, time_taken, rate):
    feedback = {
        "user_query": user_query,
        "response": response,
        "time_taken": time_taken,
        "rate": rate,
    }
    logger.info(f"Feedback= {feedback}")


# Generate a new response if last message is not from assistant
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            logger.info(f"User's query: {prompt}")
            # start time
            start_time = time.time()

            # chunks = []
            # for chunk in agent_executor._agent_executor.stream({"input": prompt}):
            #     chunks.append(chunk)
            #     st.write(chunk)

            # streaming is done in CallbackHandlerStreaming
            response = agent_executor(prompt)
            # response = agent.invoke({"input": prompt})
            # end time
            end_time = time.time()
            time_taken = end_time - start_time
            logger.info(f"Time taken to generate a response: {time_taken} seconds")

            # TODO query to trigger pdf 'Transponder beantragen' or 'Anmeldeformular Masterarbeit Universität Osnabrück'
            # TODO handle the case where there are multiple PDF files in the response
            # TODO if pdf is too long to display, provide a download link
            # check if the response contains a PDF file

            if "sources" in response:
                if response["sources"]:
                    with st.expander("Sources"):
                        for source in response["sources"]:
                            st.write(f"- {source}")

            # Comment out the following code block to disable the PDF download feature
            # pdf_content, pdf_file_name = extract_pdf_with_timeout(
            #     response["output"], 15
            # )
            # if pdf_content:

            #     st.download_button(
            #         label=f"Download: {pdf_file_name}",
            #         data=pdf_content,
            #         file_name=pdf_file_name,
            #         mime="application/pdf",
            #     )

    col1, col2, col3, col4 = st.columns([3, 3, 0.5, 0.5])
    with col3:
        st.button(
            ":thumbsup:",
            on_click=get_feedback,
            args=[prompt, response["output"], time_taken, "like"],
            help="Click here if you like the response",
        )

    with col4:
        st.button(
            ":thumbsdown:",
            on_click=get_feedback,
            args=[prompt, response["output"], time_taken, "dislike"],
            help="Click here if you dislike the response",
        )

    message = {"role": "assistant", "content": response["output"]}
    st.session_state.messages.append(message)
