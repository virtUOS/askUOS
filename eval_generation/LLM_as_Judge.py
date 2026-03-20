import os
import sys

import pandas as pd
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import csv
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from streamlit.testing.v1 import AppTest

DeprecationWarning
from src.chatbot.agents.graph import CampusManagementAgent
from src.chatbot.prompt.main import get_system_prompt
from src.chatbot.prompt.prompt_date import get_current_date
from src.config.core_config import settings
from synthetic_data_gen.utils import MixinSyntheticDataGen


@dataclass
class TestDataPoint:
    question: str
    expected_answer: str


@dataclass
class ChatbotResponse:
    answer: str


class SemanticEvaluationResult(BaseModel):
    similarity_score: int = Field(
        ...,
        description="Score from 1-5 indicating semantic similarity between expected and chatbot answers",
    )
    explanation: str = Field(
        ..., description="Detailed explanation of the similarity evaluation"
    )


class SemanticEvaluator(MixinSyntheticDataGen):

    def __init__(self, **kwargs) -> None:
        self._setup_llm(**kwargs)
        self._setup_prompt()

    def _setup_prompt(self) -> None:
        """Setup the prompt template for semantic similarity evaluation."""
        self.evaluation_prompt = PromptTemplate(
            template="""
<ROLE>
You are an expert evaluator specializing in semantic similarity assessment. Your task is to determine how semantically similar two answers are, regardless of their exact wording.
</ROLE>

<TASK>
Evaluate the semantic similarity between the expected answer and the chatbot's answer. Focus on meaning, completeness, and factual accuracy.
</TASK>

<EVALUATION_CRITERIA>
Score from 0.0 to 1.0:
- **5**: Semantically equivalent - same meaning, complete information
- **4**: Highly similar - covers main points with minor differences
- **3**: Moderately similar - covers most key points but misses some details
- **2**: Partially similar - some correct information but significant gaps
- **1**: No similarity - completely different or incorrect information

</EVALUATION_CRITERIA>

<INPUT>
**Question**: {question}

**Expected Answer**: {expected_answer}

**Chatbot Answer**: {chatbot_answer}
</INPUT>

<INSTRUCTIONS>
1. Compare the core meaning and factual content
2. Consider completeness of information
3. Ignore stylistic differences and exact wording
4. Focus on whether the chatbot answer would satisfy the user's information need
5. Provide a clear explanation for your score
</INSTRUCTIONS>

Evaluate the semantic similarity and provide your assessment.
            """,
            input_variables=["question", "expected_answer", "chatbot_answer"],
        )

    def load_test_data(self, csv_file_path: str) -> List[TestDataPoint]:
        """Load test data from CSV file."""
        test_data = []

        with open(csv_file_path, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                test_data.append(
                    TestDataPoint(
                        question=row["question"],
                        expected_answer=row["answer"],
                    )
                )

        return test_data

    def evaluate_response(
        self, test_point: TestDataPoint, chatbot_response: str
    ) -> SemanticEvaluationResult:
        """Evaluate semantic similarity of a single response."""

        llm_structured_output = self.client.with_structured_output(
            SemanticEvaluationResult
        )
        chain = self.evaluation_prompt | llm_structured_output

        response = chain.invoke(
            {
                "question": test_point.question,
                "expected_answer": test_point.expected_answer,
                "chatbot_answer": chatbot_response,
            }
        )

        return response

    def evaluate_dataset(
        self, test_data: List[TestDataPoint], save_results_path: str
    ) -> Dict[str, Any]:
        """Evaluate a complete dataset and return aggregated results."""

        agent = CampusManagementAgent.run()
        thread_id = 1
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.application.recursion_limit,  # This amounts to two laps of the graph # https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
        }

        current_date = get_current_date(settings.language.lower())

        conversation_summary = None
        history = (
            []
        )  # system_user_prompt = get_prompt(history + [("user", user_input)])

        results = []
        low_scores = []
        total_similarity = 0

        for test_point in tqdm(test_data, desc="LLM-Judge Evaluation"):
            user_input = test_point.question
            system_user_prompt = get_system_prompt(
                conversation_summary, history, user_input, current_date
            )

            try:
                chatbot_response = agent._graph.invoke(
                    {
                        "messages": system_user_prompt,
                        "message_history": history,
                        "user_initial_query": user_input,
                        "current_date": current_date,
                    },
                    config=config,
                )
                chatbot_response = chatbot_response["messages"][0].content
            except Exception as e:
                print(f"Error processing question '{test_point.question}': {e}")
                continue

            evaluation = self.evaluate_response(test_point, chatbot_response)
            results.append(
                {
                    "test_point": test_point,
                    "evaluation": evaluation,
                    "chatbot_response": chatbot_response,
                }
            )

            total_similarity += evaluation.similarity_score
            if evaluation.similarity_score <= 3:
                low_scores.append(
                    {
                        "question": test_point.question,
                        "expected_answer": test_point.expected_answer,
                        "chatbot_answer": chatbot_response,
                        "evaluation": evaluation,
                    }
                )

        # Calculate averages
        num_results = len(results)
        avg_similarity = total_similarity / num_results

        print(f"Low Similarity Scores (<=3): {len(low_scores)}")

        print(
            f"Average Similarity Score: {avg_similarity} over {num_results} evaluations."
        )

        self.save_results(results, save_results_path)

    def save_results(self, results: List[Dict[str, Any]], output_path: str) -> None:
        """Save evaluation results to a CSV file using pandas."""
        data = []
        for i, result in enumerate(results):
            question = result["test_point"].question
            expected_answer = result["test_point"].expected_answer
            chatbot_response = result["chatbot_response"]
            similarity_score = result["evaluation"].similarity_score
            explanation = result["evaluation"].explanation
            data.append(
                {
                    "question_id_q": i,
                    "question": question,
                    "human_answer": expected_answer,
                    "chatbot_answer": chatbot_response,
                    "similarity_score": similarity_score,
                    "explanation": explanation,
                }
            )
        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False)


# Example usage function
def run_semantic_evaluation(save_results_path, test_data_path):
    """Example of how to use the semantic evaluation system."""

    # Initialize the evaluator
    evaluator = SemanticEvaluator(model_name="gpt-4o-mini")

    # Load test data
    test_data = evaluator.load_test_data(test_data_path)

    # Evaluate
    evaluator.evaluate_dataset(test_data[:1], save_results_path)


if __name__ == "__main__":
    save_results_path = "/app/evaluation/RAG_evaluation/results"
    test_data_path = "/app/synthetic_data_gen/test_data/examination_regulations_general_parse_test_data.csv"
    run_semantic_evaluation(save_results_path, test_data_path)
