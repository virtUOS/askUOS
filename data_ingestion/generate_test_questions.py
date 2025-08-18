import glob
import os

import requests
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from data_ingestion.utils import get_db_id
from src.config.core_config import settings

MODEL_NAME = "google/gemma-3-27b-it"


class TestSample(BaseModel):
    question: str = Field(..., description="The question to be tested")
    answer: str = Field(..., description="The expected answer for the question")
    source: str = Field(
        ..., description="The source content from which the question is derived"
    )


class TestQuestionGenerator:
    def __init__(
        self,
    ):
        self.model = MODEL_NAME
        self._setup_llm()
        self._setup_prompt()

    def _setup_llm(self) -> None:
        """Setup language model client."""
        self.client = ChatOpenAI(
            base_url=os.getenv("VLLM_BASE_URL"),
            api_key=os.getenv("VLLM"),
            model=self.model,
            temperature=0,
        )
        self.llm_structured_output = self.client.with_structured_output(TestSample)

    def _setup_prompt(self) -> None:
        """Setup the prompt template for FAQ classification."""
        self.prompt = PromptTemplate(
            template="""
            You are a helpful assistant that generates test questions based on the provided content.
            The resulting questions/answer pair will be used to test a chatbot's abitility to answer questions based on some context.
            
            Follow these instructions and pay attention to the example below:
            1. Generate a question that is relevant to the content provided.
            2. Provide an expected answer that you must extract from the content.
            3. Ensure the question is clear and unambiguous. Do not prefix the question with 'According to the content' or similar phrases.
            4. The expected answer should be a direct response to the question.
            5. The question should be designed to test the chatbot's understanding of the content.
            6. Extract the source of the information. This you will find at the beginning of the content, usually in the form of a URL or document title.
            ------------------
            Example:
            Question: How can I apply to Doctorate? 
            Expected Answer: The first step in starting a Doctorate is to obtain a commitment from a university lecturer to supervise your doctoral thesis. You should discuss your topic with potential supervisors to ensure their research areas align with your interests .
            This confirmation of supervision should be recorded in writing on the Confirmation of Supervision (PDF, 12.81 kB) form .
            Once you have this confirmation, you can apply for __ acceptance as a doctoral candidate (PDF, 210 kB)__ . This requires submitting the signed confirmation of supervision to the Chair of the Doctoral Committee at the relevant school, along with proof of completion of an __ Individual Doctoral Development Plan (IDP)__ , 
            a copy of your Master’s certificate (certified if from another university), and a completed __ questionnaire for the doctoral student statistics (PDF, 126 kB)__ .
            After acceptance as a doctoral candidate, you can enrol for a doctorate at the Admissions
      
            ------------------
            Generate a question and an expected answer based on the following content:
            {content}
            """,
            input_variables=["content"],
        )

    def generate_test_questions(self, content: str):

        chain = self.prompt | self.llm_structured_output
        response = chain.invoke({"content": content})
        return response

    def save_test_samples_to_csv(self, test_samples, file_path):
        """Save the generated test samples to a CSV file."""
        import pandas as pd

        df = pd.DataFrame([sample.dict() for sample in test_samples])
        df.to_csv(file_path, index=False)
        print(f"Test samples saved to {file_path}")

    def main(self, directory_path):
        """Main function to generate test questions from files in a directory."""
        test_samples = []
        file_pattern = os.path.join(directory_path, "*.md")
        file_paths = glob.glob(file_pattern)

        for file_path in file_paths:
            with open(file_path, "r") as file:
                content = file.read()
                response = self.generate_test_questions(content)
                test_samples.append(response)
                print(f"Generated question: {response.question}")
                print(f"Expected answer: {response.answer}")

        self.save_test_samples_to_csv(test_samples, "test_samples.csv")


if __name__ == "__main__":
    directory_path = "/app/data_ingestion/faqs_output_md"
    generator = TestQuestionGenerator()
    generator.main(directory_path)
