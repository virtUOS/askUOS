import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch

# print(f'Python version: {sys.path}')

sys.path.append("./")
from src.chatbot.tools.search_web_tool import SearchUniWebTool


class TestWebSearch(unittest.TestCase):
    def setUp(self):
        self.search_tool = SearchUniWebTool()

    @patch("src.chatbot.tools.search_web_tool.settings")
    # receives the mock objects as parameters in the reverse order of their respective @patch decorators
    async def test_generate_summary(self, mock_settings):
        # Mock settings
        mock_settings.model.context_window = 1000

        # Input data (Text generated with gpt)
        text = """
        Applying to a university is an important step in pursuing higher education and can often be a complex process. The first phase involves researching potential universities and programs to determine the best fit for your academic and career goals. Once you have a list of prospects, you'll need to gather necessary materials, such as transcripts, letters of recommendation, and, in some cases, standardized test scores. Crafting a compelling personal statement or essay is another critical component, where you can showcase your achievements, aspirations, and unique qualities. It's important to pay close attention to application deadlines and to ensure that all materials are submitted on time. Financial aid and scholarships may also require separate applications, so it's essential to be organized and thorough. After submitting your applications, the waiting period begins, culminating in decisions that could shape the next chapter of your educational journey.
        """
        question = "What is the main point?"

        # Call the method
        result = await self.search_tool.generate_summary(text, question)

        self.assertLess(
            len(result),
            len(text),
            "The summary should be shorter than the provided text",
        )


if __name__ == "__main__":
    unittest.main()
