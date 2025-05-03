import sys

sys.path.append("./")
import time
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from langchain.evaluation import load_evaluator
from streamlit.testing.v1 import AppTest

from pages.ask_uos_chat import MAX_MESSAGE_HISTORY
from src.chatbot.agents.utils.agent_helpers import llm
from tests.warm_up import warm_up_queries


class BaseTestStreamlitApp(unittest.TestCase):

    def test_several_users(self):

        at1 = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90).run()
        at2 = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90).run()
        at3 = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90).run()

        apps = [[at1, 0], [at2, 0], [at3, 0]]

        def get_query():
            for q in warm_up_queries:
                yield q

        query_generator = get_query()
        while True:
            try:

                for at in apps:
                    # initial message count
                    at[1] = len(at[0].session_state["messages"]) or 0
                    test_query = next(query_generator)
                    at[0].chat_input[0].set_value(test_query).run()
                    assert not at[0].exception
                    # check if the message count increased
                    # each iteration generates two messages: user and assistant
                    self.assertGreater(len(at[0].session_state["messages"]), at[1])
                    # check if the message saved to the session state is the same as the one sent
                    # by the user
                    user_query = at[0].session_state["messages"][-2]["content"]
                    self.assertEqual(user_query, test_query)

                    if at[1] >= MAX_MESSAGE_HISTORY:
                        # number of expected summaries given the number of messages
                        self.assertEqual(
                            len(at[0].session_state["conversation_summary"]),
                            int(
                                len(at[0].session_state["messages"])
                                / MAX_MESSAGE_HISTORY
                            ),
                        )

                    # TODO CHECK IF THE GENERATED ANSWERS HAS ANYTHING TO DO WITH THE QUERY
                    time.sleep(2)
            except StopIteration:
                break

        for at in apps:
            summary_length = []
            for s in at[0].session_state["conversation_summary"]:
                summary_length.append(llm().get_num_tokens(s))
            print(f"Summary length (tokens): {summary_length}")

    # def test_multiple_queries(self):
    #     _llm = llm()
    #     summary_length = []
    #     at = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=60).run()
    #     initial_message_count = len(at.session_state["messages"])
    #     for index, q in enumerate(warm_up_queries):
    #         at.chat_input[0].set_value(q).run()
    #         assert not at.exception
    #         self.assertGreater(len(at.session_state["messages"]), initial_message_count)
    #         initial_message_count = len(at.session_state["messages"])
    #         # Each iteration generates two messages: user and assistant
    #         if index * 2 >= MAX_MESSAGE_HISTORY:
    #             # number of expected summaries given the number of messages
    #             self.assertEqual(
    #                 len(at.session_state["conversation_summary"]),
    #                 int(len(at.session_state["messages"]) / MAX_MESSAGE_HISTORY),
    #             )

    #     for s in at.session_state["conversation_summary"]:
    #         summary_length.append(_llm.get_num_tokens(s))

    #     print(f"Summary length (tokens): {summary_length}")

    @patch("src.chatbot.prompt.main.settings")
    @patch("pages.language.settings")
    def test_english(self, mock_settings, mock_language):
        mock_settings.language = "English"
        mock_language.language = "English"
        at = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90)
        at.session_state["selected_language"] = "English"
        at.run()
        assert not at.exception

        initial_message_count = len(at.session_state["messages"])

        question1 = "what are the application deadlines for the Biology program?"
        at.chat_input[0].set_value(question1).run()
        self.assertGreater(len(at.session_state["messages"]), initial_message_count)

        # Test references
        self.assertGreaterEqual(len(at.expander), 1)


if __name__ == "__main__":

    unittest.main()
    print()
