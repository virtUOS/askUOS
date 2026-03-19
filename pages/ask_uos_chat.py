import asyncio
import os
import time
import uuid
from typing import Optional

import nest_asyncio
import requests
import streamlit as st
from langchain_core.messages import HumanMessage
from openai import AsyncOpenAI
from streamlit import session_state
from streamlit_cookies_controller import CookieController, RemoveEmptyElementContainer

from pages.utils import initialize_session_sate, load_css, setup_page
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

# max number of messages after which a summary is generated
MAX_MESSAGES_PER_USER = 150  # Limit for the number of messages per user (Redis)
HUMAN_AVATAR = "./static/Icon-User.svg"
ASSISTANT_AVATAR = "./static/Icon-chatbot.svg"
ROLES = ("assistant", "user")
# Note: for security reasons, thread endpoints (fastapi-redis user history) is only accessible from localhost
# if fastapi runs on different container the history access logic needs to be adapted.
API_URL = "http://localhost:8000/v1"
askUOS_API_KEY = os.getenv("STREAMLIT_API_KEY", "")


# Apply nest_asyncio to allow nested event loops (Streamlit compatibility)
nest_asyncio.apply()


# TODO : Remove all the display references logic once streamlit integrates pull request  Fix st.chat_input collapse after submit #12081


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
            self.controller = CookieController()
            load_css()

    def get_client(self) -> AsyncOpenAI:
        """Returns a reusable OpenAI client pointing at your backend."""
        if "openai_client" not in st.session_state:
            st.session_state["openai_client"] = AsyncOpenAI(
                base_url=API_URL,
                api_key=askUOS_API_KEY,  # your API key
            )
        return st.session_state["openai_client"]

    def get_api_session(self) -> requests.Session:
        """Return a shared session per user, creating it once."""
        if "api_session" not in st.session_state:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {askUOS_API_KEY}",
                }
            )
            st.session_state.api_session = session
        return st.session_state.api_session

    def _run_async(self, coro):
        """
        Safely run an async coroutine in Streamlit's environment.
        Streamlit may already have a running event loop, so we handle both cases.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # nest_asyncio allows us to call run_until_complete
            # even if a loop is already running
            return loop.run_until_complete(coro)
        else:
            return asyncio.run(coro)

    def _validate_user_id(self, user_id: str) -> Optional[str]:
        """Validate that the user_id is a valid UUID string."""

        if not user_id or not isinstance(user_id, str):
            return None
        try:
            # This will raise ValueError if not a valid UUID
            val = uuid.UUID(user_id)
            return str(val)  # Return the normalized UUID string
        except (ValueError, TypeError):
            return None

    def get_history(self, user_id: str) -> list:
        validated_user_id = self._validate_user_id(user_id)
        if not validated_user_id:
            logger.warning(f"[AUTH] Invalid user_id attempted: {user_id!r}")
            st.warning(
                "Invalid session. Please refresh the page or clear your browser cookies."
            )
            st.stop()
        try:
            session = self.get_api_session()
            response = session.get(API_URL + f"/threads/{user_id}/messages")
            if response.status_code == 200:
                data = response.json()
                return data["messages"]
        except Exception as e:
            logger.error(f"[API-REDIS] Error retrieving chat history for user: {e}")
            st.warning(
                "There was an error while loading previous messages. If this issue persists, try using a different browser or contact support."
            )
            st.stop()

    def get_user_id(self) -> str:
        """Get the user ID from cookies or generate a new one, handling Streamlit rerun and returning users."""

        # If already in session_state, use it
        if (
            "ask_uos_user_id" in st.session_state
            and st.session_state["ask_uos_user_id"]
        ):
            return st.session_state["ask_uos_user_id"]

        # Try to get from cookies
        ask_uos_user_id = self.controller.get("ask_uos_user_id")
        if ask_uos_user_id:
            st.session_state["ask_uos_user_id"] = ask_uos_user_id
            return ask_uos_user_id

        # If we haven't tried waiting for the cookie yet, do so now
        if not st.session_state.get("_uos_cookie_waited", False):
            st.session_state["_uos_cookie_waited"] = True
            st.stop()  # Wait for browser to send cookies on next run

        # If we already waited and still no cookie, generate a new one
        user_id = str(uuid.uuid4())
        self.controller.set("ask_uos_user_id", user_id, max_age=60 * 60 * 24 * 365)
        st.session_state["ask_uos_user_id"] = user_id
        return user_id

    def show_warning(self):
        """Display a warning message to the user."""

        if session_state.get("show_warning", True) is False:
            return

        # Always check the cookie first
        warning_cookie = self.controller.get("ask_uos_warning_accepted")

        # Only accept the expected value, ignore anything else
        if warning_cookie is not None:
            if warning_cookie == "accepted":
                session_state["show_warning"] = False
                return
            else:
                # Malformed or tampered cookie, remove it
                self.controller.remove("ask_uos_warning_accepted")

        # Only show the warning if not already accepted
        if session_state.get("show_warning", True):
            st.warning(
                session_state["_"](
                    "The responses from the chat assistant may be incorrect - therefore, please verify the answers for their correctness."
                )
            )
            if st.button(session_state["_"]("I understand")):
                # Set the cookie BEFORE updating session_state and rerunning

                self.controller.set(
                    "ask_uos_warning_accepted", "accepted", max_age=60 * 60 * 24 * 90
                )
                session_state["show_warning"] = False
                st.rerun()

    def display_chat_messages(self):
        """Display chat messages stored in the session state."""

        user_id = self.get_user_id()
        messages: list = self.get_history(user_id)

        # use to save user-assistant message to the logs e.g., when user leaves feedback
        # st.session_state["messages"] = []

        greeting_message = session_state["_"](
            "Hello! I am happy to assist you with questions about the University of Osnabrück, including information about study programs, application processes, and admission requirements. \n How can I help you today?"
        )
        # st.session_state["messages"].append(greeting_message)
        with st.chat_message(ROLES[0], avatar=ASSISTANT_AVATAR):
            st.markdown(greeting_message)

        for m in messages:
            role = m["role"]
            if role == ROLES[1]:  # "user"
                # st.session_state["messages"].append(m)
                with st.chat_message(role, avatar=HUMAN_AVATAR):
                    st.write(m["content"])

            elif role == ROLES[0]:  # "assistant"

                if isinstance(m["content"], str):
                    content = m["content"]
                else:
                    content = m["content"][0]["text"]

                # st.session_state["messages"].append(m)
                with st.chat_message(role, avatar=ASSISTANT_AVATAR):
                    st.write(content)

            else:
                logger.error(
                    f"[LANGGRAPH] Unknown message type: {m.type}. Expected one of {ROLES}."
                )

    def handle_user_input(self):
        """Handle user input and generate a response using async astream."""

        # user_id = self.get_user_id()
        # history = self.get_history(user_id)
        if prompt := st.chat_input(
            placeholder=session_state["_"]("Message"),
            key=f"chat_input_{st.session_state.input_key_counter}",
        ):

            if not session_state.feedback_saved:
                self.log_feedback()
            st.session_state.feedback_saved = False
            st.session_state.user_feedback_faces = None
            st.session_state.user_feedback_form = None

            # history.add_user_message(prompt)
            # st.session_state["messages"].append(HumanMessage(content=prompt))

            with st.chat_message(ROLES[1], avatar="./static/Icon-User.svg"):
                st.write(prompt)
                # if history.messages[-1].type != ROLES[0]:  # "ai"
            self._run_async(self.generate_response_async(prompt))

            # TODO: DELETE ?
            st.session_state.input_key_counter += 1
            st.rerun()  # Rerun to update the chat messages and input field

    async def generate_response_async(self, prompt: str):
        """Generate a response from the assistant based on user prompt, using astream."""

        client = self.get_client()
        user_id = self.get_user_id()
        language = session_state.get("selected_language", "Deutsch")

        with st.chat_message(ROLES[0], avatar="./static/Icon-chatbot.svg"):
            with st.spinner(session_state["_"]("Generating response...")):
                message_placeholder = st.empty()
                response = ""
                start_time = time.time()
                settings.time_request_sent = start_time

                try:
                    stream = await client.chat.completions.create(
                        model="askUOS-agent",
                        messages=[{"role": "user", "content": prompt}],
                        stream=True,
                        extra_body={
                            "thread_id": user_id,
                            "language": language,
                        },
                    )

                    async for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            response += delta.content
                            message_placeholder.markdown(response)

                except Exception as e:
                    logger.error(f"[STREAMLIT] Error in streaming: {e}")
                    if not response:
                        response = session_state["_"](
                            "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
                        )
                        message_placeholder.markdown(response)

                end_time = time.time()
                time_taken = end_time - start_time
                session_state["time_taken"] = time_taken
                logger.info(f"[METRICS] Response time: {time_taken:.2f}s")

                self.store_response(response, prompt)

    def store_response(
        self,
        output: str,
        prompt: str,
    ):
        """Store the assistant's response and prompt in session state."""

        # Log user query and bot answer
        logger.info(f"[USERQUERY] User's query: {prompt}")
        logger.info(f"[BOTANSWER] Assistant's response: {output}")

        st.session_state.user_query = prompt
        st.session_state.response = output

    def show_feedback_faces(self):
        """Display feedback faces for user interaction."""

        msg = st.session_state["_"](
            "You have selected a rating of **{}** out of 5. Thank you for your feedback!"
        )
        selected = st.feedback("faces", key="user_feedback_faces")
        if selected is not None:
            try:
                st.markdown(msg.format(selected + 1))
            except Exception as e:
                logger.error(f"[FEEDBACK] Error displaying feedback message: {e}")

    def ask_further_feedback(self):
        if (
            "user_feedback_faces" in session_state
            and session_state.user_feedback_faces is not None
        ):

            if 0 <= session_state.user_feedback_faces <= 4:

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

        if (
            "user_feedback_faces" in session_state
            and session_state.user_feedback_faces is not None
        ):

            feedback = {}
            # There are five faces, so the score is between 0 and 4. 4 being the best score
            if 0 <= session_state.user_feedback_faces <= 4:
                feedback["score"] = session_state.user_feedback_faces

            if session_state.user_feedback_form:
                feedback["text_rating"] = session_state.user_feedback_form

            if (
                0 <= session_state.user_feedback_faces <= 4
                or session_state.user_feedback_form
            ):

                feedback["user_query"] = session_state.user_query
                feedback["response"] = st.session_state.response
                feedback["time_taken"] = session_state.time_taken

                logger.info(f"[FEEDBACK] Feedback= {feedback}")
                session_state.feedback_saved = True

    @st.dialog("ask.UOS")
    def delete_chat_history(self):
        """Display a dialog to confirm chat history deletion."""

        if "delete" in st.query_params:
            st.query_params.delete = "false"
        message = (
            settings.chat_page.delete_message_dialog_box_german
            if settings.language == "Deutsch"
            else settings.chat_page.delete_message_dialog_box_english
        )
        st.markdown(message)
        if st.button(
            session_state["_"]("Delete"),
            key="confirm_delete_chat",
            use_container_width=True,
        ):
            user_id = self.get_user_id()
            session = self.get_api_session()
            response = session.delete(
                f"{API_URL}/threads/{user_id}/messages",
            )
            if response.status_code == 200:
                logger.debug("History deleted")
            # history = self.get_history(user_id)
            # history.clear()
            st.session_state["messages"] = []
            st.rerun()
        if st.button(
            session_state["_"]("Cancel"),
            key="cancel_delete_chat",
            use_container_width=True,
        ):
            st.rerun()

    def show_delete_button(self):
        """Display a delete button below the chat input, full width and horizontal."""
        # Add a small space
        if st.button(
            f'🗑️ {session_state["_"]("Clear chat history")}',
            key="delete_chat",
            help=session_state["_"]("Clear all chat history"),
        ):
            self.delete_chat_history()
        st.write("")  # Add a small space

    def run(self):
        """Main method to run the application logic."""
        with st.container(key="page-header-container"):
            st.title("ask.UOS")
        initialize_session_sate()
        RemoveEmptyElementContainer()
        # Get or create user ID using our method
        # user_id = self.get_user_id()

        # self.show_warning()

        # self.initialize_chat(user_id)
        self.display_chat_messages()
        self.handle_user_input()
        self.show_feedback_faces()
        self.ask_further_feedback()

        if st.query_params.get("delete", "false") == "true":
            # If delete query param is set, show the delete dialog
            self.delete_chat_history()

        if st.query_params.get("in_widget", "false") == "false":
            # If not in widget mode, show the delete button
            self.show_delete_button()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
