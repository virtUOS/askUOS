import sys

sys.path.append("/app")

import sys
from typing import List

from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent

warm_up_queries = [
    "What are the application deadlines for the fall and spring semesters for the Computer Science Program?",
    "Was kann ich tun, wenn ich keinen Studienplatz im Master Sport bekommen habe?",
    "hi",
    "According to the examination regulations, can I write my Master's thesis in English?, Mathematics",
    "How do I apply for on-campus housing, and what meal plans are available?",
    "According to the examination regulations, how are the thesis and oral exam graded?, Mathematics",
]


def warm_up_agent(warm_up_queries: List[str]) -> None:
    """
    Downloads models and  prepare the agent for actual tasks.

    Parameters:
    warm_up_queries (List[str]): A list of queries to be executed during the warm-up phase.

    Returns:
    None
    """
    graph = CampusManagementOpenAIToolsAgent.run()
    # Warm-up phase
    for q in warm_up_queries:
        _ = graph(q)  # Execute warm-up queries, timing not recorded
        print("Warm-up query executed successfully.")
    print("Warm-up phase completed successfully.")


if __name__ == "__main__":

    warm_up_agent(warm_up_queries)
