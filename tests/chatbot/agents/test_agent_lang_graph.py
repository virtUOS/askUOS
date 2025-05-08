import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent
from src.config.core_config import settings


class TestCampusManagementOpenAIToolsAgent(unittest.TestCase):

    def setUp(self):
        # Initialize the agent with a default language
        self.agent = CampusManagementOpenAIToolsAgent.run(language="English")

    def test_filter_messages_within_limit(self):
        messages = [
            SystemMessage(content="System message"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]
        filtered_messages = self.agent.filter_messages(messages, k=5)
        self.assertEqual(len(filtered_messages), 3)
        self.assertEqual(filtered_messages[0].content, "System message")
        self.assertEqual(filtered_messages[1].content, "Hello")
        self.assertEqual(filtered_messages[2].content, "Hi there!")

    def test_filter_messages_exceeding_limit_with_system_message(self):
        messages = [
            SystemMessage(content="System message"),
            HumanMessage(content="1"),
            AIMessage(content="2"),
            HumanMessage(content="3"),
            AIMessage(content="4"),
            HumanMessage(content="5"),
            AIMessage(content="6"),
        ]
        filtered_messages = self.agent.filter_messages(messages, k=3)
        self.assertEqual(len(filtered_messages), 4)
        self.assertEqual(filtered_messages[0].content, "System message")
        self.assertEqual(filtered_messages[1].content, "4")
        self.assertEqual(filtered_messages[2].content, "5")
        self.assertEqual(filtered_messages[3].content, "6")

    def test_filter_messages_exceeding_limit_without_system_message(self):
        messages = [
            HumanMessage(content="1"),
            AIMessage(content="2"),
            HumanMessage(content="3"),
            AIMessage(content="4"),
            HumanMessage(content="5"),
            AIMessage(content="6"),
        ]
        filtered_messages = self.agent.filter_messages(messages, k=3)
        self.assertEqual(len(filtered_messages), 3)
        self.assertEqual(filtered_messages[0].content, "4")
        self.assertEqual(filtered_messages[1].content, "5")
        self.assertEqual(filtered_messages[2].content, "6")

    def test_shorten_conversation_summary(self):
        """
        Test the shorten_conversation_summary method of the CampusManagementOpenAIToolsAgent class.

        """

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]
        with patch("src.chatbot.agents.agent_lang_graph.MAX_TOKEN_SUMMARY", 2):
            with patch(
                "src.chatbot.agents.agent_lang_graph.CampusManagementOpenAIToolsAgent.shorten_conversation_summary"
            ) as mock_shorten:
                mock_shorten.return_value = AIMessage(content="Shortened Summary")
                summary = self.agent.summarize_conversation(messages)
                mock_shorten.assert_called_once()

            self.assertIn("Shortened Summary", summary)

        print(summary)

    # @patch.object(CampusManagementOpenAIToolsAgent, "shorten_conversation_summary")
    # @patch.object(CampusManagementOpenAIToolsAgent, "_llm")
    # def test_summarize_conversation(self, mock_llm, mock_shorten_conversation_summary):
    #     # Mock the LLM and shorten_conversation_summary methods
    #     mock_llm.get_num_tokens.return_value = 500  # Tokens less than MAX_TOKEN_SUMMARY
    #     mock_shorten_conversation_summary.return_value = "Shortened Summary"

    #     # Mock the chain object and its invoke method
    #     mock_chain = MagicMock()
    #     mock_response = MagicMock()
    #     mock_chain.invoke.return_value = mock_response
    #     mock_response.content = "Test Summary"

    #     messages = [
    #         HumanMessage(content="Hello"),
    #         AIMessage(content="Hi there!"),
    #     ]
    #     summary = self.agent.summarize_conversation(messages)
    #     self.assertEqual(summary, "**Summary of conversation earlier:** Test Summary")
    #     mock_chain.invoke.assert_called()
    #     mock_shorten_conversation_summary.assert_not_called()

    #     # Test when tokens exceed MAX_TOKEN_SUMMARY
    #     mock_llm.get_num_tokens.return_value = 1500
    #     summary = self.agent.summarize_conversation(messages)
    #     mock_shorten_conversation_summary.assert_called()
    #     self.assertIn("Shortened Summary", summary)


if __name__ == "__main__":
    unittest.main()
    print()
