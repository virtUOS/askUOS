import time
import uuid
from typing import Dict, List, Optional

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from streamlit import session_state
from streamlit_feedback import streamlit_feedback

from pages.utils import initialize_session_sate, load_css, setup_page

# from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent
from src.chatbot.prompt.main import get_system_prompt
from src.chatbot.prompt.prompt_date import get_current_date
from src.chatbot.tools.utils.exceptions import ProgrammableSearchException
from src.chatbot.tools.utils.tool_helpers import (
    do_not_visit_links,
    visited_docs,
    visited_links,
)
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings


class ChatApp:
    """
    ChatApp represents a chat application using Streamlit. It handles the initialization, user interaction, and response generation for a chat assistant.

    Attributes:
        _instance (Optional[ChatApp]): Instance of the ChatApp class.

    """

    _instance: Optional["ChatApp"] = None

    def __new__(cls) -> "ChatApp":
        if cls._instance is None:
            cls._instance = super(ChatApp, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self.__dict__:

            setup_page()
            load_css()

    def show_warning(self):
        """Display a warning message to the user."""
        if session_state.get("show_warning", True):
            st.warning(
                session_state["_"](
                    "The responses from the chat assistant may be incorrect - therefore, please verify the answers for their correctness."
                )
            )
            if st.button(session_state["_"]("I understand")):
                session_state["show_warning"] = False
                st.rerun()

    def initialize_chat(self):
        """Initialize the chat messages in session state if not present."""
        if "messages" not in st.session_state:
            greeting_message = session_state["_"](
                "Hello! I am happy to assist you with questions about the University of Osnabrück, including information about study programs, application processes, and admission requirements. \n How can I help you today?"
            )
            st.session_state["messages"] = [
                {
                    "role": "assistant",
                    "avatar": "./static/Icon-chatbot.svg",
                    "content": greeting_message,
                }
            ]

    def display_chat_messages(self):
        """Display chat messages stored in the session state."""
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"], avatar=message["avatar"]):
                st.write(message["content"])

    def handle_user_input(self):
        """Handle user input and generate a response."""
        if prompt := st.chat_input(placeholder=session_state["_"]("Message")):
            if not session_state.feedback_saved:
                self.log_feedback()
            st.session_state.feedback_saved = False
            st.session_state.user_feedback_faces = None
            st.session_state.user_feedback_form = None

            st.session_state.messages.append(
                {"role": "user", "content": prompt, "avatar": "./static/Icon-User.svg"}
            )
            with st.chat_message("user", avatar="./static/Icon-User.svg"):
                st.write(prompt)

            if st.session_state.messages[-1]["role"] != "assistant":
                self.generate_response(prompt)

    def generate_response(self, prompt):
        """Generate a response from the assistant based on user prompt."""

        graph = CampusManagementOpenAIToolsAgent.run(
            language=session_state["selected_language"]
        )

        def stream_graph_updates(user_input):
            response = ""
            to_stream = ""
            thread_id = 1
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": settings.application.recursion_limit,  # This amounts to two laps of the graph # https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
            }
            if settings.application.tracing:
                from opik.integrations.langchain import OpikTracer

                tracer = OpikTracer(
                    graph=graph._graph.get_graph(xray=True),
                    project_name=settings.application.opik_project_name,
                )

                config["callbacks"] = [tracer]
            current_date = get_current_date(settings.language.lower())
            history = self._get_chat_history(st.session_state["messages"])
            # system_user_prompt = get_prompt(history + [("user", user_input)])
            system_user_prompt = get_system_prompt(history, user_input, current_date)
            table_content = ""
            is_table_content = False
            # deleteme = []

            def _get_stream():
                do_not_visit_links.clear()
                for msg, metadata in graph._graph.stream(
                    {
                        "messages": system_user_prompt,
                        "message_history": history,
                        "user_initial_query": user_input,
                        "current_date": current_date,
                    },
                    stream_mode="messages",
                    config=config,
                ):

                    if (
                        msg.content
                        and not isinstance(msg, HumanMessage)
                        and not isinstance(msg, ToolMessage)
                        and (
                            metadata["langgraph_node"] == "generate"
                            or metadata["langgraph_node"] == "generate_application"
                        )
                    ):
                        # deleteme.append(msg.content)
                        yield msg.content

            try:

                gen_stream = _get_stream()
                for msg in gen_stream:
                    response += msg

                    # streaming of every line
                    if msg == "|":
                        is_table_content = True
                        table_content += msg
                        while is_table_content:
                            try:
                                msg = next(gen_stream)
                                table_content += msg
                                response += msg
                                # do not delete the blank space at the beginning of ' |\n\n'
                                # it is used to identify the end of the table
                                if msg == " |\n\n":
                                    # end of table

                                    st.markdown(table_content)
                                    table_content = ""
                                    is_table_content = False
                            except StopIteration:
                                if table_content:
                                    st.markdown(table_content)
                                    table_content = ""
                                is_table_content = False
                                break

                    if "\n" in msg:
                        to_stream += msg
                        st.markdown(to_stream)
                        to_stream = ""
                    else:
                        to_stream += msg

                    print(msg, end="|", flush=True)

                # the agent did not use any tools
                if graph._agent_direct_msg:
                    response = graph._agent_direct_msg
                    st.markdown(response)
                    graph._agent_direct_msg = None

                # print(
                #     f"-----------------------------{deleteme}----------------------------"
                # )

            # try:
            #     graph._graph.invoke(
            #         {
            #             "messages": system_user_prompt,
            #             "user_initial_query": user_input,
            #             "current_date": current_date,
            #         },
            #         stream_mode="messages",
            #         config=config,
            #     )
            #     response = graph._curated_answer
            #     st.markdown(response)
            #     print()

            except GraphRecursionError as e:
                # TODO handle recursion limit error
                logger.exception(f"Recursion Limit reached: {e}")
                response = session_state["_"](
                    "I'm sorry, but I couldn't find enough information to fully answer your question. Could you please try rephrasing your query and ask again?"
                )
                st.markdown(response)
                # clear the docs references
                visited_docs.clear()

            except ProgrammableSearchException as e:
                response = session_state["_"](
                    "I'm sorry, something went wrong while connecting to the data provided. If the error persists, please reach out to the administrators for assistance."
                )
                st.markdown(response)
                # clear the docs references
                visited_docs.clear()

            except Exception as e:
                logger.exception(f"Error while processing the user's query: {e}")
                response = session_state["_"](
                    "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
                )
                # clear the docs references
                visited_docs.clear()
                st.markdown(response)

            return response, to_stream

        with st.chat_message("assistant", avatar="./static/Icon-chatbot.svg"):
            with st.spinner(session_state["_"]("Generating response...")):
                logger.info(f"User's query: {prompt}")

                start_time = time.time()
                settings.time_request_sent = start_time

                response, to_stream = stream_graph_updates(prompt)
                # if there is content left, stream it
                if to_stream:
                    st.markdown(to_stream)

                end_time = time.time()
                time_taken = end_time - start_time
                session_state["time_taken"] = time_taken
                logger.info(
                    f"Time taken to serve whole answer to the user: {time_taken} seconds"
                )

                self.store_response(response, prompt)
                if visited_docs():
                    self.display_visited_docs()

                if visited_links():
                    self.display_visited_links()

            # self.store_response(response, prompt)

    def _get_chat_history(self, messages: List[Dict[str, str]], k=5):
        """
        Retrieve and store the last k messages from the chat history.

        Args:
            messages (List[Dict[str, str]]): A list of message dictionaries, where each dictionary contains
                                             'role', 'content' and 'avatar' keys representing the role of the message
                                             sender and the message content respectively. The 'avatar' key represents the icon used when displaying the message.
            k (int, optional): The number of most recent messages to retain. Defaults to 5.

        Returns:
            None
        """

        if not messages:
            return []

        if len(messages) > k:
            messages = messages[-k:]  # get the last k messages
        # chat_history = [
        #     {"role": record["role"], "content": record["content"]}
        #     for record in messages
        # ]
        chat_history = []
        for record in messages:
            if record["role"] == "user":
                chat_history.append(
                    HumanMessage(content=record["content"], additional_kwargs={})
                )
            elif record["role"] == "assistant":
                chat_history.append(
                    AIMessage(content=record["content"], additional_kwargs={})
                )
            else:
                chat_history.append(
                    ToolMessage(content=record["content"], additional_kwargs={})
                )

        logger.debug(f"Chat History -------{chat_history}--------")
        return chat_history

    def display_visited_docs(self):
        """Display the documents visited for the current user query."""

        references = visited_docs.format_references()
        reference_examination_regulations = "https://www.uni-osnabrueck.de/studium/im-studium/zugangs-zulassungs-und-pruefungsordnungen/"
        message = session_state["_"](
            "The information provided draws on the documents below that can be found in the [University Website]({}). We encourage you to visit the site to explore these resources for additional details and insights!"
        )

        st.markdown(message.format(reference_examination_regulations))
        for key, value in references.items():
            # TODO add translation
            page_label = (
                session_state["_"]("Pages")
                if len(value) > 1
                else session_state["_"]("Page")
            )
            page_list = ", ".join(map(str, value))
            # TODO: Remove page numbers, these are wrong. Temporary
            # st.markdown(f"- **{key}**,  **{page_label}**: {page_list}")
            st.markdown(f"- **{key}**")
        visited_docs.clear()

    def display_visited_links(self):
        """Display the links visited for the current user query."""

        with st.expander(session_state["_"]("Sources")):
            for link in visited_links():
                st.markdown(
                    f"""
                    
                        <div class="truncate">
                            <span>&#8226;</span> <a href="{link}" target="_blank" rel="noopener noreferrer">{link}</a>
                        </div>
                    
                        """,
                    unsafe_allow_html=True,
                )
        visited_links.clear()

    def store_response(self, output, prompt):
        """Store the assistant's response and prompt in session state."""
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": output,
                "avatar": "./static/Icon-chatbot.svg",
            }
        )
        st.session_state.user_query = prompt

    def show_feedback_faces(self):
        streamlit_feedback(
            feedback_type="faces",
            key="user_feedback_faces",
        )

    def ask_further_feedback(self):
        if session_state.user_feedback_faces:

            with st.expander(session_state["_"]("**Rate the response**")):

                with st.form("feedback_form", clear_on_submit=True):

                    text_rating = st.text_area(
                        "text_rating",
                        label_visibility="hidden",
                        placeholder=session_state["_"](
                            "[Optional] We look forward to your feedback"
                        ),
                        height=150,
                    )

                    if st.form_submit_button(session_state["_"]("Submit")):
                        session_state.user_feedback_form = text_rating
                        self.log_feedback()

                        st.markdown(
                            """
                            <style>
                                .stExpander {
                                    display: none;
                                }
                            </style>
                            """,
                            unsafe_allow_html=True,
                        )

    def log_feedback(self):

        feedback = {}

        if session_state.user_feedback_faces:
            feedback["score"] = session_state.user_feedback_faces["score"]

        if session_state.user_feedback_form:
            feedback["text_rating"] = session_state.user_feedback_form

        if session_state.user_feedback_faces or session_state.user_feedback_form:

            feedback["user_query"] = session_state.user_query
            feedback["response"] = st.session_state.messages[-1]["content"]
            feedback["time_taken"] = session_state.time_taken

            logger.info(f"Feedback= {feedback}")
            session_state.feedback_saved = True

    def run(self):
        """Main method to run the application logic."""
        st.title("ask.UOS")
        initialize_session_sate()
        self.show_warning()
        self.initialize_chat()
        self.display_chat_messages()
        self.handle_user_input()
        self.show_feedback_faces()
        self.ask_further_feedback()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
