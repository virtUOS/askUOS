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

        # [instance of the app,keep track of the number of messages in the session state, [user_query_1, user_query_2,...]]
        apps = [[at1, 0, []], [at2, 0, []], [at3, 0, []]]

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
                    # add the query to the list of queries
                    at[2].append(test_query)
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

                    time.sleep(2)
                # [[link_1, link_2,...],[],[]]
                visited_links = [
                    app[0].session_state["agent"]._visited_links for app in apps
                ]
                tuple_visited_links = [tuple(i) for i in visited_links if i]
                if tuple_visited_links:

                    # since the queries are different, the visited links should be different
                    self.assertEqual(
                        len(tuple_visited_links),
                        len(set(tuple_visited_links)),
                        f"The visited links are not unique across users. {visited_links}",
                    )
            except StopIteration:
                break

        for at in apps:
            # check if the number of messages is equal to the number of queries * 2 + 1 (1 accounts for the AI initial message e.g., "Hi, I am an AI assistant")
            # each iteration generates two messages: user and assistant
            self.assertEqual(
                len(at[0].session_state["messages"]),
                (len(at[2]) * 2) + 1,
                f"The number of messages is not equal to the number of queries. {at[0].session_state['messages']}",
            )
            # check if the queries are the same as the ones sent by the user
            for m in at[0].session_state["messages"]:
                if m["role"] == "user":
                    self.assertIn(m["content"], at[2])
            # TODO CHECK IF THE GENERATED ANSWERS HAve ANYTHING TO DO WITH THE QUERY

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

    def test_cache_redis(self):
        """Test Redis caching for web content and search results."""
        import asyncio

        import redis.asyncio as redis

        # Clear Redis cache before test
        async def clear_cache():
            redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)
            try:
                await redis_client.flushall()
                await redis_client.aclose()
            except Exception as e:
                print(f"Failed to clear Redis cache: {e}")

        asyncio.run(clear_cache())
        time.sleep(1)  # Allow time for cache clear to complete

        # Initialize app twice to test cache between sessions
        at1 = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90).run()
        at2 = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90).run()

        test_query = "What are the requirements for studying Computer Science?"

        # First run - no cache
        start_time1 = time.time()
        at1.chat_input[0].set_value(test_query).run()
        first_run_time = time.time() - start_time1

        # Track first run results
        first_links = at1.session_state["agent"]._visited_links
        first_response = at1.session_state["messages"][-1]["content"]

        time.sleep(1)  # Ensure cache is written

        # Second run - should use cache
        start_time2 = time.time()
        at2.chat_input[0].set_value(test_query).run()
        second_run_time = time.time() - start_time2

        # Get results from second run
        second_links = at2.session_state["agent"]._visited_links
        second_response = at2.session_state["messages"][-1]["content"]

        # Verify cache is working
        self.assertEqual(
            first_links,
            second_links,
            "Visited links should be identical when using cache",
        )

        # Time comparison
        self.assertLess(
            second_run_time,
            first_run_time,
            "Second run should be significantly faster due to caching",
        )

        # Verify no exceptions occurred
        assert not at1.exception
        assert not at2.exception


if __name__ == "__main__":

    unittest.main()
    print()
