import sys
print(f'Python version: {sys.path}')

sys.path.append('/Users/yesidcano/repos/chatbot/')

from agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from langchain_core.messages import AIMessage, HumanMessage
from langchain.evaluation import load_evaluator
import unittest



# python3 -m unittest

# class BaseTest(unittest.TestCase):
    
#     def setUp(self):
#         self._agent_executor = CampusManagementOpenAIToolsAgent.run()
        
        
class AgentExecutorTest(unittest.TestCase):
    
    # def setUp(self):
    #     self._agent_executor = CampusManagementOpenAIToolsAgent.run()
    
    def test_output(self):
        agent_executor = CampusManagementOpenAIToolsAgent.run()
        print('hi')
        response = agent_executor("can I study Biology?")
   
        
        # expected structure of the response
        expected_keys = ['input', 'chat_history', 'output']
        
        # Check if the actual dictionary contains the expected keys
        for key in expected_keys:
            self.assertIn(key, response, f"The key '{key}' is not present in the dictionary.")
            
        # previous chat history
        self.assertGreater(len(response), 1, "Chat history is not being kept.")
        
        # check the type of the chat_history elements
        for message in response['chat_history']:
            self.assertIsInstance(message, (AIMessage, HumanMessage), "Chat history elements are not of the correct type.")
        
        
        # test memory. Note that word 'Biology' is not used in the question, so the agent should take the context from the previous chat history
        response = agent_executor("how long does the Master take?")
        
        expected_output = """
        The Master's program in Biology at the University of Osnabrück has a standard study duration of 4 semesters. The language of instruction is primarily English, with some courses also offered in German. 
        The program provides a research-oriented specialization in current areas of molecular and organismic biology, 
        covering a broad spectrum of methodological and thematic topics.\n\nStudents have the flexibility to choose from three 
        thematic focuses: General Biology, Evolution, Behavior & Ecology, and Cell and Molecular Biology. 
        The curriculum allows for a flexible selection of modules within the chosen focus, the acquisition of interdisciplinary 
        competencies, and a strong practical component with a research emphasis.\n\nUpon completion of the Master's program, 
        graduates have diverse career opportunities in areas such as fundamental research, applied research, 
        development and distribution (e.g., pharmaceutical or agro-industry), academic teaching, 
        science journalism, and various roles in museums, health care, and public administration. 
        Additionally, the program provides a solid foundation for pursuing a doctoral degree (Ph.D.) in research.\n\nFor further details, you can visit 
        the [Biology – From Molecules to Organisms | Master of Science](https://www.uni-osnabrueck.de/studieninteressierte/studiengaenge-a-z/biologiebiology-from-molecules-to-organisms-master-of-science/) page.\n\nIf you have any more questions or need additional information, feel free to ask!""
        
        """
        
        # TODO currently uses OpenAI's embedding distance evaluator. Replace with a local model
        evaluator = load_evaluator("pairwise_embedding_distance")
        score = evaluator.evaluate_string_pairs(response['output'], expected_output)
        
        print(f"Score: {score['score']}")
        print(f'output: {response["output"]}')
        self.assertGreaterEqual(score['score'], 0.7, "The value is not greater than or equal to 0.7.")
        
        
        
        
if __name__ == '__main__':
    
    unittest.main()