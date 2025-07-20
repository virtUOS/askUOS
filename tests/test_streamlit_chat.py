import sys

sys.path.append("./")
import asyncio
import time
import unittest
import uuid
from unittest.mock import MagicMock, PropertyMock, patch

import redis.asyncio as redis
from langchain.evaluation import load_evaluator
from langchain_redis import RedisChatMessageHistory
from streamlit.testing.v1 import AppTest

from pages.ask_uos_chat import MAX_MESSAGE_HISTORY
from src.chatbot.agents.utils.agent_helpers import llm
from tests.warm_up import warm_up_queries


class BaseTestStreamlitApp(unittest.TestCase):

    def setUp(self):
        """Clear Redis cache before each test."""

        async def clear_cache():
            redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)
            try:
                await redis_client.flushall()
                await redis_client.aclose()
            except Exception as e:
                print(f"Failed to clear Redis cache: {e}")

        asyncio.run(clear_cache())
        time.sleep(0.5)  # Allow time for cache clear to complete

    def _mock_streamlit_feedback(self):
        """Helper to mock streamlit feedback function to return None safely."""
        with patch("streamlit.feedback") as mock_feedback:
            mock_feedback.return_value = None
            yield mock_feedback

    def _check_app_state(self, at, test_name=""):
        """Helper method to check app state and debug issues."""
        if at.exception:
            print(f"App exception in {test_name}: {at.exception}")
            raise at.exception

        print(f"Chat inputs available in {test_name}: {len(at.chat_input)}")
        if len(at.chat_input) == 0:
            # Try to access session state safely
            try:
                session_state_dict = dict(at.session_state)
                print(
                    f"Session state keys in {test_name}: {list(session_state_dict.keys())}"
                )
            except Exception as e:
                print(f"Could not access session state in {test_name}: {e}")

            print(
                f"Available elements in {test_name}: chat_input={len(at.chat_input)}, button={len(at.button)}, text_input={len(at.text_input)}"
            )

        return len(at.chat_input) > 0

    def test_several_users(self):
        # Mock streamlit feedback to prevent test errors
        with patch("streamlit.feedback", return_value=None):
            # Create three separate user IDs to simulate different users
            user_id1 = str(uuid.uuid4())
            user_id2 = str(uuid.uuid4())
            user_id3 = str(uuid.uuid4())

            # Mock the cookie controller to return different user IDs for each app instance
            with patch("pages.ask_uos_chat.CookieController") as mock_controller_class:
                # Create app instances with mocked user IDs
                mock_controller1 = MagicMock()
                mock_controller1.get.return_value = user_id1

                mock_controller2 = MagicMock()
                mock_controller2.get.return_value = user_id2

                mock_controller3 = MagicMock()
                mock_controller3.get.return_value = user_id3

                # Set up the controller instances to return different user IDs
                mock_controller_class.side_effect = [
                    mock_controller1,
                    mock_controller2,
                    mock_controller3,
                ]

                at1 = AppTest.from_file(
                    "/app/pages/ask_uos_chat.py", default_timeout=90
                )
                # Pre-populate session state to avoid st.stop() in get_user_id
                at1.session_state["ask_uos_user_id"] = user_id1
                at1.session_state["_uos_cookie_waited"] = True
                at1.run()
                self.assertTrue(self._check_app_state(at1, "test_several_users at1"))

                # Reset for second instance
                mock_controller_class.side_effect = [mock_controller2]
                at2 = AppTest.from_file(
                    "/app/pages/ask_uos_chat.py", default_timeout=90
                )
                at2.session_state["ask_uos_user_id"] = user_id2
                at2.session_state["_uos_cookie_waited"] = True
                at2.run()
                self.assertTrue(self._check_app_state(at2, "test_several_users at2"))

                # Reset for third instance
                mock_controller_class.side_effect = [mock_controller3]
                at3 = AppTest.from_file(
                    "/app/pages/ask_uos_chat.py", default_timeout=90
                )
                at3.session_state["ask_uos_user_id"] = user_id3
                at3.session_state["_uos_cookie_waited"] = True
                at3.run()
                self.assertTrue(self._check_app_state(at3, "test_several_users at3"))

            # [instance of the app, initial message count, [user_query_1, user_query_2,...], user_id]
            apps = [
                [at1, 0, [], user_id1],
                [at2, 0, [], user_id2],
                [at3, 0, [], user_id3],
            ]

            def get_query():
                for q in warm_up_queries:
                    yield q

            query_generator = get_query()
            while True:
                try:
                    for at in apps:
                        # Get message count from Redis history instead of session state
                        history = RedisChatMessageHistory(
                            redis_url="redis://redis:6379",
                            session_id=at[3],  # user_id
                            ttl=60 * 60 * 3,
                        )

                        at[1] = len(history.messages)
                        test_query = next(query_generator)
                        print(f"------------------- Processing query: {test_query}")

                        # add the query to the list of queries
                        at[2].append(test_query)

                        # Ensure chat input is available before using it
                        if len(at[0].chat_input) == 0:
                            print(f"No chat input available for user {at[3]}")
                            continue

                        at[0].chat_input[0].set_value(test_query).run()
                        assert not at[0].exception

                        # Refresh history after the query
                        history = RedisChatMessageHistory(
                            redis_url="redis://redis:6379",
                            session_id=at[3],  # user_id
                            ttl=60 * 60 * 3,
                        )

                        # check if the message count increased
                        # each iteration generates two messages: user and assistant
                        self.assertGreater(len(history.messages), at[1])

                        # check if the message saved to the history is the same as the one sent by the user
                        user_message = None
                        for msg in reversed(history.messages):
                            if msg.type == "human":
                                user_message = msg.content
                                break

                        self.assertEqual(user_message, test_query)

                        # Check conversation summary logic
                        if at[1] >= MAX_MESSAGE_HISTORY:
                            # Count summary messages
                            summary_count = sum(
                                1
                                for msg in history.messages
                                if hasattr(msg, "additional_kwargs")
                                and msg.additional_kwargs.get("is_summary", False)
                            )

                            # check that summary is on the right index
                            for i in range(1, summary_count + 1):

                                self.assertTrue(
                                    hasattr(
                                        history.messages[MAX_MESSAGE_HISTORY * i],
                                        "additional_kwargs",
                                    )
                                    and history.messages[
                                        MAX_MESSAGE_HISTORY * i
                                    ].additional_kwargs.get("is_summary", False),
                                    f"Expected summary message at index {(MAX_MESSAGE_HISTORY * i)}, but found: {history.messages[MAX_MESSAGE_HISTORY * i]}",
                                )

                            # since history.message contains also summary messages,
                            # the expected number of summaries is calculated as follows:
                            # (total messages - summary messages) / MAX_MESSAGE_HISTORY
                            # expected_summaries = int(
                            #     (len(history.messages) - summary_count)
                            #     / MAX_MESSAGE_HISTORY
                            # )
                            # self.assertEqual(summary_count, expected_summaries)

                        time.sleep(2)

                    # Check visited links uniqueness across users
                    visited_links = []
                    for app in apps:
                        try:
                            agent = app[0].session_state["agent"]
                            if hasattr(agent, "_visited_links"):
                                visited_links.append(agent._visited_links)
                        except (KeyError, AttributeError):
                            pass  # agent not in session state

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

            # Final verification
            histories = []
            for at in apps:
                history = RedisChatMessageHistory(
                    redis_url="redis://redis:6379",
                    session_id=at[3],  # user_id
                    ttl=60 * 60 * 3,
                )

                # Collect non-summary messages
                non_summary_messages = [
                    msg
                    for msg in history.messages
                    if not (
                        hasattr(msg, "additional_kwargs")
                        and msg.additional_kwargs.get("is_summary", False)
                    )
                ]

                # check if the number of messages is equal to the number of queries * 2 + 1
                self.assertEqual(
                    len(non_summary_messages),
                    (len(at[2]) * 2) + 1,  # +1 for initial greeting
                    f"The number of messages is not equal to the number of queries. Messages: {len(non_summary_messages)}, Queries: {len(at[2])}",
                )

                # check if the queries are the same as the ones sent by the user
                user_messages = [
                    msg.content for msg in non_summary_messages if msg.type == "human"
                ]
                for query in at[2]:
                    self.assertIn(query, user_messages)

                # Collect message contents for uniqueness check
                message_contents = {str(msg.content) for msg in non_summary_messages}
                histories.append(message_contents)

                # Log summary lengths
                summary_messages = [
                    msg
                    for msg in history.messages
                    if hasattr(msg, "additional_kwargs")
                    and msg.additional_kwargs.get("is_summary", False)
                ]
                summary_length = [
                    llm().get_num_tokens(msg.content) for msg in summary_messages
                ]
                print(f"Summary length (tokens) for user {at[3]}: {summary_length}")

            # check if the session states are different across users
            intersection = set.intersection(*histories)
            self.assertEqual(
                len(intersection),
                1,  # Only the initial greeting message should be common
                f"The session states are not different enough. Common messages: {intersection}",
            )

    @patch("src.chatbot.prompt.main.settings")
    @patch("pages.language.settings")
    def test_english(self, mock_settings, mock_language):
        # Mock streamlit feedback to prevent test errors
        with patch("streamlit.feedback", return_value=None):
            mock_settings.language = "English"
            mock_language.language = "English"

            # Mock user ID for this test
            user_id = str(uuid.uuid4())

            with patch("pages.ask_uos_chat.CookieController") as mock_controller_class:
                mock_controller = MagicMock()
                mock_controller.get.return_value = user_id
                mock_controller_class.return_value = mock_controller

                at = AppTest.from_file("/app/pages/ask_uos_chat.py", default_timeout=90)
                at.session_state["selected_language"] = "English"
                # Pre-populate session state to avoid st.stop() in get_user_id
                at.session_state["ask_uos_user_id"] = user_id
                at.session_state["_uos_cookie_waited"] = True
                at.run()

                # Check app state before proceeding
                self.assertTrue(self._check_app_state(at, "test_english"))

                # Get initial message count from Redis
                history = RedisChatMessageHistory(
                    redis_url="redis://redis:6379",
                    session_id=user_id,
                    ttl=60 * 60 * 3,
                )
                initial_message_count = len(history.messages)

                question1 = (
                    "what are the application deadlines for the Biology program?"
                )
                at.chat_input[0].set_value(question1).run()

                # Refresh history after query
                history = RedisChatMessageHistory(
                    redis_url="redis://redis:6379",
                    session_id=user_id,
                    ttl=60 * 60 * 3,
                )
                self.assertGreater(len(history.messages), initial_message_count)

                # Test references
                self.assertGreaterEqual(len(at.expander), 1)

    def test_cache_redis(self):
        """Test Redis caching for web content and search results."""
        # Mock streamlit feedback to prevent test errors
        with patch("streamlit.feedback", return_value=None):
            # Clear Redis cache before test
            async def clear_cache():
                redis_client = redis.Redis(
                    host="redis", port=6379, decode_responses=True
                )
                try:
                    await redis_client.flushall()
                    await redis_client.aclose()
                except Exception as e:
                    print(f"Failed to clear Redis cache: {e}")

            asyncio.run(clear_cache())
            time.sleep(1)  # Allow time for cache clear to complete

            # Create two different user IDs
            user_id1 = str(uuid.uuid4())
            user_id2 = str(uuid.uuid4())

            with patch("pages.ask_uos_chat.CookieController") as mock_controller_class:
                # First app instance
                mock_controller1 = MagicMock()
                mock_controller1.get.return_value = user_id1
                mock_controller_class.return_value = mock_controller1

                at1 = AppTest.from_file(
                    "/app/pages/ask_uos_chat.py", default_timeout=90
                )
                # Pre-populate session state to avoid st.stop() in get_user_id
                at1.session_state["ask_uos_user_id"] = user_id1
                at1.session_state["_uos_cookie_waited"] = True
                at1.run()
                self.assertTrue(self._check_app_state(at1, "test_cache_redis at1"))

                # Second app instance
                mock_controller2 = MagicMock()
                mock_controller2.get.return_value = user_id2
                mock_controller_class.return_value = mock_controller2

                at2 = AppTest.from_file(
                    "/app/pages/ask_uos_chat.py", default_timeout=90
                )
                at2.session_state["ask_uos_user_id"] = user_id2
                at2.session_state["_uos_cookie_waited"] = True
                at2.run()
                self.assertTrue(self._check_app_state(at2, "test_cache_redis at2"))

            test_query = "What are the requirements for studying Computer Science?"

            # First run - no cache
            start_time1 = time.time()
            at1.chat_input[0].set_value(test_query).run()
            first_run_time = time.time() - start_time1

            # Track first run results
            first_links = []
            second_links = []
            try:
                agent = at1.session_state["agent"]
                if hasattr(agent, "_visited_links"):
                    first_links = agent._visited_links
            except (KeyError, AttributeError):
                pass  # agent not in session state

            # Get first response from Redis
            history1 = RedisChatMessageHistory(
                redis_url="redis://redis:6379",
                session_id=user_id1,
                ttl=60 * 60 * 3,
            )
            first_response = None
            for msg in reversed(history1.messages):
                if msg.type == "ai":
                    first_response = msg.content
                    break

            time.sleep(1)  # Ensure cache is written

            # Second run - should use cache
            start_time2 = time.time()
            at2.chat_input[0].set_value(test_query).run()
            second_run_time = time.time() - start_time2

            # Get results from second run
            try:
                agent = at2.session_state["agent"]
                if hasattr(agent, "_visited_links"):
                    second_links = agent._visited_links
            except (KeyError, AttributeError):
                pass  # agent not in session state

            history2 = RedisChatMessageHistory(
                redis_url="redis://redis:6379",
                session_id=user_id2,
                ttl=60 * 60 * 3,
            )
            second_response = None
            for msg in reversed(history2.messages):
                if msg.type == "ai":
                    second_response = msg.content
                    break

            # Verify cache is working
            # self.assertEqual(
            #     first_links,
            #     second_links,
            #     "Visited links should be identical when using cache",
            # )
            count = 0
            for link in first_links:
                if link in second_links:
                    count += 1
            self.assertGreater(
                count,
                2,
                "There should be at least two links in common between the two runs",
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
