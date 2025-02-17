import time
import uuid
from typing import Dict, List, Optional

import streamlit as st
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from streamlit import session_state
from streamlit_feedback import streamlit_feedback

from pages.utils import initialize_session_sate, load_css, setup_page

# from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent
from src.chatbot.prompt.main import get_prompt
from src.chatbot.tools.utils.tool_helpers import visited_links
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
                "Hello! I am happy to assist you with questions about the University of Osnabrück, including information about study programs, application processes, admission requirements and other university-related topics. \n How can I help you today?"
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
            st.session_state.messages.append(
                {"role": "user", "content": prompt, "avatar": "./static/Icon-User.svg"}
            )
            with st.chat_message("user", avatar="./static/Icon-User.svg"):
                st.write(prompt)

            if st.session_state.messages[-1]["role"] != "assistant":
                self.generate_response(prompt)

    def log_feedback(self):
        """Log user feedback."""
        if session_state.user_feedback:
            feedback = {
                "user_query": session_state.user_query,
                "response": st.session_state.messages[-1]["content"],
                "time_taken": session_state.time_taken,
                "rate": session_state.user_feedback["score"],
            }
            session_state.user_feedback = None
            logger.info(f"Feedback= {feedback}")

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
                "recursion_limit": 12,  # This amounts to two laps of the graph (+2 supersteps), since we have 5 super steps, # https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
            }
            history = self._get_chat_history(st.session_state["messages"])
            # system_user_prompt = get_prompt(history + [("user", user_input)])
            system_user_prompt = get_prompt(history)
            try:
                for msg, metadata in graph._graph.stream(
                    {
                        "messages": system_user_prompt,
                        "user_initial_query": user_input,
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
                            or metadata["langgraph_node"] == "agent_node"
                        )
                    ):
                        response += msg.content
                        # streaming of every line
                        if "\n" in msg.content:
                            to_stream += msg.content
                            st.markdown(to_stream)
                            to_stream = ""
                        else:
                            to_stream += msg.content

                        print(msg.content, end="|", flush=True)

            except GraphRecursionError as e:
                # TODO handle recursion limit error
                logger.error(f"Recursion Limit reached: {e}")
                response = session_state["_"](
                    "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
                )

            except Exception as e:
                logger.error(f"Error while processing the user's query: {e}")
                response = session_state["_"](
                    "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
                )
            return response, to_stream

        with st.chat_message("assistant", avatar="./static/Icon-chatbot.svg"):
            with st.spinner(session_state["_"]("Generating response...")):
                logger.info(f"User's query: {prompt}")

                start_time = time.time()
                settings.time_request_sent = start_time
                # TODO temporary fix: simulate streaming with streamlit. Get all answer and then stream it
                # ------------------
                # thread_id = 1
                # config = {
                #     "configurable": {"thread_id": thread_id},
                #     "recursion_limit": 25,
                # }
                # # TODO add history here
                # history = self._get_chat_history(st.session_state["messages"])

                # system_user_prompt = get_prompt(history + [("user", prompt)])

                # try:

                #     graph_response = graph._graph.invoke(
                #         {"messages": system_user_prompt}, config=config
                #     )
                #     response = graph_response["messages"][-1].content
                # except Exception as e:
                #     logger.error(f"Error while processing the user's query: {e}")
                #     response = session_state["_"](
                #         "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
                #     )

                # def stream():
                #     for word in response.split(" "):
                #         yield word + " "
                #         time.sleep(0.02)

                # TODO temporary fix: simulate streaming with streamlit. Get all answer and then stream it
                # st.write_stream(stream)

                # st.markdown(response)

                # ------------------
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

                if visited_links():
                    self.display_visited_links()

            self.store_response(response, prompt)

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

        chat_history = [
            {"role": record["role"], "content": record["content"]}
            for record in messages
        ]

        logger.debug(f"Chat History -------{chat_history}--------")
        return chat_history

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
        streamlit_feedback(feedback_type="faces", key="user_feedback")

    def run(self):
        """Main method to run the application logic."""
        st.title("Ask.UOS")
        initialize_session_sate()
        self.show_warning()
        self.initialize_chat()
        self.display_chat_messages()
        self.handle_user_input()
        self.log_feedback()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
