import sys

sys.path.append("./")
import time
import unittest
from unittest.mock import MagicMock, patch

from langchain.evaluation import load_evaluator
from streamlit.testing.v1 import AppTest

from tests.warm_up import warm_up_queries


class BaseTestStreamlitApp(unittest.TestCase):

    def test_multiple_queries(self):
        at = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90).run()
        initial_message_count = len(at.session_state["messages"])
        for q in warm_up_queries:
            at.chat_input[0].set_value(q).run()
            assert not at.exception
            self.assertGreater(len(at.session_state["messages"]), initial_message_count)
            initial_message_count = len(at.session_state["messages"])

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
