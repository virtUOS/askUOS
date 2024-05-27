from streamlit.testing.v1 import AppTest
from langchain.evaluation import load_evaluator
import time
import unittest



class BaseTestStreamlitApp(unittest.TestCase):
    

    def test_output(self):

        at = AppTest.from_file('pages/streamlit_chat.py', default_timeout=30).run()

        at.chat_input[0].set_value('can I study Biology?').run()

        # test memory
        at.chat_input[0].set_value('how long does the Master take?').run()

        time.sleep(5)
        
        # test output
        expected_output = "The Master's program in Biology at the University of Osnabrück has a standard study period of 4 semesters. The language of instruction is primarily English, with some courses offered in German. The program provides a research-oriented specialization in current areas of molecular and organismic biology, covering a broad methodological and thematic spectrum. This includes topics ranging from structural biology and biophysical fundamentals to cell biology, physiological phenomena, ecological, evolutionary, and behavioral biological questions.\n\nThe Master's program offers three thematic focal points: (1) General Biology, (2) Evolution, Behavior & Ecology, and (3) Cell and Molecular Biology. It also includes flexible module options within the chosen focus, interdisciplinary skills development, a strong practical component with a research focus, and the opportunity to conduct thesis work in an excellent research environment with access to state-of-the-art laboratory infrastructure.\n\nUpon completion of the Master's program, graduates have diverse career opportunities in areas such as fundamental research at universities and other research institutions, applied research, development, and distribution (e.g., pharmaceutical or agro-industry), teaching in an academic environment, science journalism, work as an expert (e.g., state criminal investigation department, environmental assessments), employment in museums, zoological or botanical gardens, healthcare, and public administration.\n\nFor further information about the Master's program, access to study plans, admission requirements, and application procedures, you can contact the academic advising office for Biology or the student representatives in the Biology student council.\n\nIf you need more details, you can visit the [University of Osnabrück's Biology Department website](https://www.uni-osnabrueck.de/studieninteressierte/studiengaenge-a-z/biologiebiology-from-molecules-to-organisms-master-of-science/) for additional information.\n\nIf you have any other questions or need further assistance, feel free to ask!"
            
        # extract the response from the session state
        response = at.session_state['messages'][4]['content']
        evaluator = load_evaluator("pairwise_embedding_distance")
        score = evaluator.evaluate_string_pairs(prediction=response, prediction_b=expected_output)

        self.assertGreaterEqual(score['score'], 0, "The value is not greater than or equal to 0.")
        self.assertIn('Biology' or 'biology', response)

     


if __name__ == '__main__':
    
    unittest.main()
    print()