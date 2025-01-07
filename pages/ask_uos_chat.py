import time
from typing import Optional
import streamlit as st
from streamlit import session_state
from src.config.core_config import settings
from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from src.chatbot.tools.utils.tool_helpers import visited_links
from src.chatbot_log.chatbot_logger import logger
from pages.utils import initialize_session_sate, setup_page, load_css
from streamlit_feedback import streamlit_feedback


class ChatApp:
    """
    ChatApp represents a chat application using Streamlit. It handles the initialization, user interaction, and response generation for a chat assistant.

    Attributes:
        _instance (Optional[ChatApp]): Instance of the ChatApp class.
        agent_executor (Callable): Function to execute the chat agent.

    """

    _instance: Optional["ChatApp"] = None

    def __new__(cls) -> "ChatApp":
        if cls._instance is None:
            cls._instance = super(ChatApp, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self.__dict__:
            setup_page()
            initialize_session_sate()
            self.agent_executor = CampusManagementOpenAIToolsAgent.run()
            load_css()
            self.show_warning()
            self.initialize_chat()

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
            greeting_message = session_state["_"]("How can I help you?")
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
        with st.chat_message("assistant", avatar="./static/Icon-chatbot.svg"):
            with st.spinner(session_state["_"]("Generating response...")):
                logger.info(f"User's query: {prompt}")

                start_time = time.time()
                settings.time_request_sent = start_time

                response = self.agent_executor(prompt)

                end_time = time.time()
                time_taken = end_time - start_time
                session_state["time_taken"] = time_taken
                logger.info(
                    f"Time taken to serve whole answer to the user: {time_taken} seconds"
                )

                if visited_links():
                    self.display_visited_links()

            self.store_response(response["output"], prompt)

    def display_visited_links(self):
        """Display the links visited for the current user query."""
        with st.expander(session_state["_"]("Sources")):
            for link in visited_links():
                st.write("- " + link)
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
        self.display_chat_messages()
        self.handle_user_input()
        self.log_feedback()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
