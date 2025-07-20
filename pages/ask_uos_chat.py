import time
import uuid
from collections import deque
from typing import Dict, List, Optional

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_redis import RedisChatMessageHistory
from langgraph.errors import GraphRecursionError
from streamlit import session_state
from streamlit_cookies_controller import (CookieController,
                                          RemoveEmptyElementContainer)

from pages.utils import initialize_session_sate, load_css, setup_page
# from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from src.chatbot.agents.agent_lang_graph import \
    CampusManagementOpenAIToolsAgent
from src.chatbot.agents.utils.exceptions import MaxMessageHistoryException
from src.chatbot.prompt.main import get_system_prompt
from src.chatbot.prompt.prompt_date import get_current_date
from src.chatbot.tools.utils.exceptions import ProgrammableSearchException
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

# max number of messages after which a summary is generated
MAX_MESSAGE_HISTORY = 5

HUMAN_AVATAR = "./static/Icon-User.svg"
ASSISTANT_AVATAR = "./static/Icon-chatbot.svg"
ROLES = ("ai", "human")


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
            # setup_page()
            self.controller = CookieController()
            load_css()

    def get_history(self, user_id: str) -> RedisChatMessageHistory:
        #  TODO: catch error when the client sends a cookie that is not a valid UUID
        history = RedisChatMessageHistory(
            redis_url="redis://redis:6379",
            session_id=user_id,
            ttl=60 * 60 * 3,  # 3 hours
        )
        return history

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
        if session_state.get("show_warning", True):
            st.warning(
                session_state["_"](
                    "The responses from the chat assistant may be incorrect - therefore, please verify the answers for their correctness."
                )
            )
            if st.button(session_state["_"]("I understand")):
                session_state["show_warning"] = False
                st.rerun()

    def initialize_chat(self, ask_uos_user_id: str):
        """Initialize the chat messages in session state if not present."""

        history = self.get_history(ask_uos_user_id)

        if not history.messages:
            # If no messages in history, initialize with a greeting message
            greeting_message = session_state["_"](
                "Hello! I am happy to assist you with questions about the University of Osnabrück, including information about study programs, application processes, and admission requirements. \n How can I help you today?"
            )
            history.add_ai_message(greeting_message)

        # if "messages" not in st.session_state:
        #     greeting_message = session_state["_"](
        #         "Hello! I am happy to assist you with questions about the University of Osnabrück, including information about study programs, application processes, and admission requirements. \n How can I help you today?"
        #     )
        #     st.session_state["messages"] = [
        #         {
        #             "role": "assistant",
        #             "avatar": "./static/Icon-chatbot.svg",
        #             "content": greeting_message,
        #         }
        #     ]
        # if "conversation_summary" not in st.session_state:
        #     st.session_state["conversation_summary"] = []

    def display_chat_messages(self):
        """Display chat messages stored in the session state."""

        user_id = self.get_user_id()
        history = self.get_history(user_id)
        # stores the summary messages
        st.session_state["conversation_summary"] = []
        # human and assistant/ai messages (these are used in the system prompt)
        st.session_state["messages"] = []
        # all messages from the history, see ROLES
        messages = history.messages

        for m in messages:
            role = m.type
            if role == ROLES[1]:  # "human"
                st.session_state["messages"].append(m)
                with st.chat_message(role, avatar=HUMAN_AVATAR):
                    st.write(m.content)

            elif role == ROLES[0]:  # "ai"
                # check if the message is a summary
                if m.additional_kwargs.get("is_summary", False):
                    st.session_state["conversation_summary"].append(m.content)

                else:
                    st.session_state["messages"].append(m)
                    with st.chat_message(role, avatar=ASSISTANT_AVATAR):
                        st.write(m.content)

            else:
                logger.error(
                    f"Unknown message type: {m.type}. Expected one of {ROLES}."
                )

        # for message in st.session_state["messages"]:
        #     with st.chat_message(message["role"], avatar=message["avatar"]):
        #         st.write(message["content"])

    def handle_user_input(self):
        """Handle user input and generate a response."""

        user_id = self.get_user_id()
        history = self.get_history(user_id)

        if prompt := st.chat_input(placeholder=session_state["_"]("Message")):
            if not session_state.feedback_saved:
                self.log_feedback()
            st.session_state.feedback_saved = False
            st.session_state.user_feedback_faces = None
            st.session_state.user_feedback_form = None

            history.add_user_message(prompt)
            st.session_state["messages"].append(HumanMessage(content=prompt))
            # st.session_state.messages.append(
            #     {"role": "user", "content": prompt, "avatar": "./static/Icon-User.svg"}
            # )
            with st.chat_message(ROLES[1], avatar="./static/Icon-User.svg"):
                st.write(prompt)

            if history.messages[-1].type != ROLES[0]:  # "ai"
                self.generate_response(prompt)

            # if st.session_state.messages[-1]["role"] != "assistant":
            #     self.generate_response(prompt)

    def get_agent(self):
        if st.session_state["agent"] is None:
            st.session_state["agent"] = CampusManagementOpenAIToolsAgent.run(
                language=session_state["selected_language"]
            )
            st.session_state["agent_language"] = session_state["selected_language"]

        if st.session_state["selected_language"] != st.session_state["agent_language"]:
            st.session_state["agent_language"] = st.session_state["selected_language"]
            st.session_state["agent"] = CampusManagementOpenAIToolsAgent.run(
                language=session_state["selected_language"]
            )
        return st.session_state["agent"]

    def generate_response(self, prompt):
        """Generate a response from the assistant based on user prompt."""

        graph = self.get_agent()

        further_help_msg = session_state["_"](
            """If you need personal assistance regarding studying at the university, you can visit the [StudiOS]({}) (Studierenden-Information Osnabrück) or [ZSB]({}) (Zentrale Studienberatung Osnabrück) website."""
        )
        further_help_msg = further_help_msg.format(
            "https://www.uni-osnabrueck.de/universitaet/organisation/studierenden-information-osnabrueck-studios/",
            "https://www.zsb-os.de/",
        )

        # graph = CampusManagementOpenAIToolsAgent.run(
        #     language=session_state["selected_language"]
        # )

        def stream_graph_updates(user_input):
            response = ""
            to_stream = ""
            # TODO USE THE ID RETRIEVED FROM COOKIE CONTROLLER
            thread_id = 1
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": settings.application.recursion_limit,  # This amounts to two laps of the graph # https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
            }
            # if settings.application.tracing:
            #     from opik.integrations.langchain import OpikTracer

            #     tracer = OpikTracer(
            #         graph=graph._graph.get_graph(xray=True),
            #         project_name=settings.application.opik_project_name,
            #     )

            #     config["callbacks"] = [tracer]
            current_date = get_current_date(settings.language.lower())

            conversation_summary = (
                st.session_state["conversation_summary"][-1]
                if st.session_state.get("conversation_summary", None)
                else None
            )
            # messages that are not still summarized. remaining_msg = len(messages) - (MAX_MESSAGE_HISTORY * number_of_summaries); IF remaining_msg ==0 return the last two messages
            history = self._get_conversation_history(st.session_state["messages"])
            # system_user_prompt = get_prompt(history + [("user", user_input)])

            system_user_prompt = get_system_prompt(
                conversation_summary, history, user_input, current_date
            )
            table_content = ""
            is_table_content = False
            # deleteme = []

            def _get_stream():
                # if there are links from the previous query, clear them
                graph._visited_links = []
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
                            or metadata["langgraph_node"]
                            == "generate_teaching_degree_node"
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
                st.markdown(f"{response}\n\n{further_help_msg}")
                # clear the docs references
                graph._visited_docs.clear()

            except ProgrammableSearchException as e:
                response = session_state["_"](
                    "I'm sorry, something went wrong while connecting to the data provided. If the error persists, please reach out to the administrators for assistance."
                )
                st.markdown(f"{response}\n{further_help_msg}")
                # clear the docs references
                graph._visited_docs.clear()

            except Exception as e:
                logger.exception(f"Error while processing the user's query: {e}")
                response = session_state["_"](
                    "I'm sorry, but I am unable to process your request right now. Please try again later or consider rephrasing your question."
                )
                # clear the docs references
                graph._visited_docs.clear()
                st.markdown(f"{response}\n{further_help_msg}")

            return response, to_stream

        with st.chat_message(ROLES[0], avatar="./static/Icon-chatbot.svg"):
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

                self.store_response(response, prompt, graph)
                if graph._visited_docs():
                    self.display_visited_docs()

                if graph._visited_links:
                    self.display_visited_links()

            # self.store_response(response, prompt)

    def display_visited_docs(self):
        """Display the documents visited for the current user query."""

        graph = self.get_agent()
        references = graph._visited_docs.format_references()
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
        graph._visited_docs.clear()

    def display_visited_links(self):
        """Display the links visited for the current user query."""

        graph = self.get_agent()
        with st.expander(session_state["_"]("Sources")):
            for link in graph._visited_links:
                st.markdown(
                    f"""

                        <div class="truncate">
                            <span>&#8226;</span> <a href="{link}" target="_blank" rel="noopener noreferrer">{link}</a>
                        </div>

                        """,
                    unsafe_allow_html=True,
                )

    def store_response(
        self,
        output: str,
        prompt: str,
        graph: CampusManagementOpenAIToolsAgent,
    ):
        """Store the assistant's response and prompt in session state."""

        user_id = self.get_user_id()
        history_redis = self.get_history(user_id)

        # store the response in the Redis chat history
        history_redis.add_ai_message(output)

        # st.session_state.messages.append(
        #     {
        #         "role": "assistant",
        #         "content": output,
        #         "avatar": "./static/Icon-chatbot.svg",
        #     }
        # )
        st.session_state.user_query = prompt

        # summarize the conversation
        number_of_summaries = len(
            st.session_state["conversation_summary"]
        )  # number of summaries
        if (
            len(history_redis.messages) >= MAX_MESSAGE_HISTORY
            # and len(st.session_state.messages) % MAX_MESSAGE_HISTORY == 0
            and (number_of_summaries * MAX_MESSAGE_HISTORY + MAX_MESSAGE_HISTORY)
            <= len(history_redis.messages)
        ):

            if number_of_summaries == 0:

                summary_msg = AIMessage(
                    content=graph.summarize_conversation(history_redis.messages),
                    additional_kwargs={"is_summary": True},
                )
                history_redis.add_message(summary_msg)

                # st.session_state["conversation_summary"].append(
                #     graph.summarize_conversation(
                #         history,
                #     )
                # )
            else:
                # if there is a previoius summary, update it
                summary_msg = AIMessage(
                    content=graph.summarize_conversation(
                        history_redis.messages[
                            -MAX_MESSAGE_HISTORY * number_of_summaries :
                        ],
                        st.session_state["conversation_summary"][
                            -1
                        ],  # get the last summary
                    ),
                    additional_kwargs={"is_summary": True},
                )
                history_redis.add_message(summary_msg)

                # st.session_state["conversation_summary"].append(
                #     graph.summarize_conversation(
                #         self._get_chat_history(
                #             history_redis.messages[
                #                 -MAX_MESSAGE_HISTORY * number_of_summaries :
                #             ]
                #         ),
                #         st.session_state["conversation_summary"][
                #             -1
                #         ],  # get the last summary
                #     )
                # )
            # TODO if a summary is generated, MAKE SURE THAT THE SUMMARY IS NOT GREATER THAT MAX_TOKEN_SUMMARY. IF IT IS, THEN summarize it again

    # TODO: DELETE FUNCTION. Objects are already saved to REDIS using the right type
    # def _convert_messages(self, messages: List) -> List:

    #     chat_history = []
    #     for record in messages:
    #         if record.type == ROLES[0] or record.type == ROLES[1]:
    #             chat_history.append(record)

    #         elif record.type == ROLES[2]:  # "summary"
    #             continue  # excludes # "summary"
    #         else:
    #             chat_history.append(
    #                 ToolMessage(content=record["content"], additional_kwargs={})
    #             )

    #     logger.debug(f"Chat History -------{chat_history}--------")
    #     return chat_history

    # def _get_chat_history(self, messages: List, k=MAX_MESSAGE_HISTORY):
    #     """
    #     Retrieve and store the last k messages from the chat history.

    #     Args:
    #         messages (List[Dict[str, str]]): A list of message dictionaries, where each dictionary contains
    #                                          'role', 'content' and 'avatar' keys representing the role of the message
    #                                          sender and the message content respectively. The 'avatar' key represents the icon used when displaying the message.

    #     """

    #     if not messages:
    #         return []

    #     # if len(messages) > k:
    #     #     messages = messages[-k:]  # get the last k messages
    #     # chat_history = [
    #     #     {"role": record["role"], "content": record["content"]}
    #     #     for record in messages
    #     # ]

    #     return self._convert_messages(messages)

    def _get_conversation_history(self, history: List):
        """
        history: Filtered HumanMessage and AIMessage objects from the chat history.
        """
        if st.session_state.get("conversation_summary", None):

            # number of summarized messages
            k = len(st.session_state["conversation_summary"]) * MAX_MESSAGE_HISTORY

            if len(history) > k:
                # messages that have not been summarized yet
                conversation_history = history[k:]  # get the last k messages

                # conversation_history = deque(conversation_history)
                # # Two ai messages cannot be consecutive
                # if isinstance(conversation_history[0], AIMessage):
                #     new_ai_message = AIMessage(
                #         content=st.session_state["conversation_summary"][-1]
                #         + "\n\n"
                #         + conversation_history[0].content
                #     )

                #     conversation_history[0] = new_ai_message
                # else:
                #     conversation_history.appendleft(
                #         AIMessage(content=st.session_state["conversation_summary"][-1])
                #     )

            else:
                # when there is only a summary, append the last two messages

                conversation_history = []
                # conversation_history.append(
                #     AIMessage(content=st.session_state["conversation_summary"][-1])
                # )
                try:
                    conversation_history.append(history[-2])
                    conversation_history.append(history[-1])
                except IndexError:
                    raise MaxMessageHistoryException(
                        "MAX_MESSAGE_HISTORY must be >= 2. Summarizing only allowed when there are 2 or more messages."
                    )

        else:
            conversation_history = history

        return conversation_history

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
                logger.error(f"Error displaying feedback message: {e}")

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
                feedback["response"] = st.session_state.messages[-1].content
                feedback["time_taken"] = session_state.time_taken

                logger.info(f"Feedback= {feedback}")
                session_state.feedback_saved = True

    def run(self):
        """Main method to run the application logic."""
        st.title("ask.UOS")
        initialize_session_sate()
        RemoveEmptyElementContainer()
        # Get or create user ID using our method
        user_id = self.get_user_id()
        self.show_warning()
        # DO NOT CHANGE THE ORDER IN WHICH THESE METHODS ARE CALLED
        self.initialize_chat(user_id)
        self.display_chat_messages()
        self.handle_user_input()
        self.show_feedback_faces()
        self.ask_further_feedback()


if __name__ == "__main__":
    app = ChatApp()
    app.run()


# Check if we're in a test environment
# import sys
# if 'pytest' in sys.modules or 'unittest' in sys.modules or 'streamlit.testing' in sys.modules:
#     return
