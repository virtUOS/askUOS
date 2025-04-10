import asyncio
import json
import os

import pandas as pd
from langchain_openai import ChatOpenAI
from ragas.dataset_schema import EvaluationDataset, MultiTurnSample, SingleTurnSample
from ragas.llms import LangchainLLMWrapper
from ragas.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from ragas.metrics import TopicAdherenceScore

# from src.chatbot.utils.agent_helpers import llm as evaluator_llm

evaluator_llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini"))


read_csv = pd.read_csv("evaluation/ragas_eval/agent_logs.csv")
REFERENCE_TOPICS = [
    "University support",
    "Course information",
    "Student life",
    "Accommodation",
    "Application process",
]


def create_samples():
    samples = []
    for i in range(len(read_csv)):
        row = read_csv.iloc[i]
        row_json = json.loads(row["output_messages"])
        sample = []
        for j in row_json:
            if j["type"] == "ai":
                ai_message = AIMessage(
                    content=j["content"],
                    tool_calls=j["tool_calls"],
                    metadata=j["response_metadata"],
                )
                sample.append(ai_message)
            elif j["type"] == "human":
                human_message = HumanMessage(content=j["content"])
                sample.append(human_message)
            elif j["type"] == "tool":
                tool_message = ToolMessage(content=j["content"])
                sample.append(tool_message)
        samples.append(sample)

    return samples


async def evaluate_topic_adherence():

    samples = create_samples()
    scores = []
    for sample in samples:

        try:
            sample_eval = MultiTurnSample(
                user_input=sample, reference_topics=REFERENCE_TOPICS
            )
            scorer = TopicAdherenceScore(llm=evaluator_llm, mode="precision")
            s = await scorer.multi_turn_ascore(sample_eval)
            print(s)
            scores.append(s)

        except Exception as e:
            print(f"Error: {e}")

        print(scores)
        print("\n")

    print(f"Average score: {sum(scores) / len(scores)}")


if __name__ == "__main__":

    os.environ["LANGSMITH_TRACING"] = "false"
    asyncio.run(evaluate_topic_adherence())
    print("done")

    # os.environ["LANGSMITH_TRACING"] = "true"
