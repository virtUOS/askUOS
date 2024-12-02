import sys

# print(f'Python version: {sys.path}')

sys.path.append("./")

from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from src.chatbot.tools.search_web_tool import extract_and_visit_links
from test.search_sample import search_sample, expected_result
from langchain_core.messages import AIMessage, HumanMessage
from langchain.evaluation import load_evaluator
from src.config.core_config import settings
import src.chatbot.utils.prompt_text as text
from src.chatbot.utils.prompt import get_prompt
import unittest


# python3 -m unittest

# class BaseTest(unittest.TestCase):

#     def setUp(self):
#         self._agent_executor = CampusManagementOpenAIToolsAgent.run()


"""
TODO 
- Test that the queries are in german
"""


class AgentExecutorTest(unittest.TestCase):

    # def setUp(self):
    #     self._agent_executor = CampusManagementOpenAIToolsAgent.run()

    def test_prompt_language(self):
        # prompt should be in english
        settings.language = "English"
        english_prompt = get_prompt()
        agent_executor = CampusManagementOpenAIToolsAgent.run()
        self.assertEqual(
            agent_executor.prompt.pretty_print(),
            english_prompt.pretty_print(),
            "The prompt is not in English.",
        )

        # prompt should be in german
        settings.language = "Deutsch"
        german_prompt = get_prompt()
        agent_executor = CampusManagementOpenAIToolsAgent.run()
        self.assertEqual(
            agent_executor.prompt.pretty_print(),
            german_prompt.pretty_print(),
            "The prompt is not in German.",
        )

    def test_results_oder(self):

        search_result_text, anchor_tags = extract_and_visit_links(search_sample)
        hrefs = [str(tag.get("href")) for tag in anchor_tags]
        self.assertEqual(hrefs, expected_result, "The anchor tags are not equal.")

    def test_output(self):
        agent_executor = CampusManagementOpenAIToolsAgent.run()

        response = agent_executor("can I study Biology?")

        # expected structure of the response
        expected_keys = ["input", "chat_history", "output"]

        # Check if the actual dictionary contains the expected keys
        for key in expected_keys:
            self.assertIn(
                key, response, f"The key '{key}' is not present in the dictionary."
            )

        # test memory. Note that word 'Biology' is not used in the question, so the agent should take the context from the previous chat history
        response = agent_executor("how long does the Master take?")

        # previous chat history
        self.assertEqual(
            len(response["chat_history"]), 2, "Chat history is not being kept."
        )

        # check the type of the chat_history elements
        for message in response["chat_history"]:
            self.assertIsInstance(
                message,
                (AIMessage, HumanMessage),
                "Chat history elements are not of the correct type.",
            )

        expected_output = "The Master's program in Biology at the University of Osnabrück has a standard study period of 4 semesters. The language of instruction is primarily English, with some courses offered in German. The program provides a research-oriented specialization in current areas of molecular and organismic biology, covering a broad methodological and thematic spectrum. This includes topics ranging from structural biology and biophysical fundamentals to cell biology, physiological phenomena, ecological, evolutionary, and behavioral biological questions.\n\nThe Master's program offers three thematic focal points: (1) General Biology, (2) Evolution, Behavior & Ecology, and (3) Cell and Molecular Biology. It also includes flexible module options within the chosen focus, interdisciplinary skills development, a strong practical component with a research focus, and the opportunity to conduct thesis work in an excellent research environment with access to state-of-the-art laboratory infrastructure.\n\nUpon completion of the Master's program, graduates have diverse career opportunities in areas such as fundamental research at universities and other research institutions, applied research, development, and distribution (e.g., pharmaceutical or agro-industry), teaching in an academic environment, science journalism, work as an expert (e.g., state criminal investigation department, environmental assessments), employment in museums, zoological or botanical gardens, healthcare, and public administration.\n\nFor further information about the Master's program, access to study plans, admission requirements, and application procedures, you can contact the academic advising office for Biology or the student representatives in the Biology student council.\n\nIf you need more details, you can visit the [University of Osnabrück's Biology Department website](https://www.uni-osnabrueck.de/studieninteressierte/studiengaenge-a-z/biologiebiology-from-molecules-to-organisms-master-of-science/) for additional information.\n\nIf you have any other questions or need further assistance, feel free to ask!"

        # TODO currently uses OpenAI's embedding distance evaluator. Replace with a local model
        evaluator = load_evaluator("pairwise_embedding_distance")
        score = evaluator.evaluate_string_pairs(
            prediction=response["output"], prediction_b=expected_output
        )

        print(f"Score: {score['score']}")
        print(f'output: {response["output"]}')
        self.assertGreaterEqual(
            score["score"], 0, "The value is not greater than or equal to 0."
        )
        self.assertIn("Biology" or "biology", response["output"])


if __name__ == "__main__":

    unittest.main()
