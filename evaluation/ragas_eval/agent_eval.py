import uuid

import ragas.messages as r
from langgraph.errors import GraphRecursionError
from ragas.dataset_schema import MultiTurnSample
from ragas.integrations.langgraph import convert_to_ragas_messages
from ragas.metrics import ToolCallAccuracy

from evaluation.ragas_eval.msg_db import queries, reference_tool_calls
from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent
from src.chatbot.prompt.main import get_prompt

if len(reference_tool_calls) != len(queries):
    raise ValueError("reference_tool_calls and queries must have the same length")


graph = CampusManagementOpenAIToolsAgent.run()
scores = []

for query, reference_tool_call in zip(queries, reference_tool_calls):
    thread_id = uuid.uuid4()
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 4,
    }

    prompt = get_prompt([("user", query)])

    try:

        response = graph._graph.invoke(
            {"messages": prompt, "user_initial_query": query}, config=config
        )

        ragas_trace = convert_to_ragas_messages(messages=response["messages"])

        sample = MultiTurnSample(
            user_input=ragas_trace,
            reference_tool_calls=[
                r.ToolCall(
                    name=reference_tool_call["name"],
                    args=reference_tool_call["args"],
                )
            ],
        )

        tool_accuracy_scorer = ToolCallAccuracy()
        score = tool_accuracy_scorer.multi_turn_score(sample)
        if score < 1:
            print(
                f"----Test failed. User query: {query}, System Query: {response['search_query']}"
            )

        scores.append(score)

    except GraphRecursionError as e:
        print(f"Recursion limit reached: {e}")

    except Exception as e:
        print(f"Error: {e}")


print(f"Average score: {sum(scores) / len(scores)}")
print(f"Median score: {sorted(scores)[len(scores) // 2]}")
