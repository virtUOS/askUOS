import sys

sys.path.append("/app")

import sys
from typing import List

from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent

warm_up_queries = [
    "Was muss ich in einem Masterstudium Informatik tun?",
    "Welche Zulassungsbeschränkungen gibt es für den Masterstudiengang Informatik?",
    "What are the application deadlines for the fall and spring semesters for the Computer Science Program?",
    "What is the tuition fee structure for the upcoming academic year?",
    "Bis wann kann ich mich exmatrikulieren lassen und mein Geld zurück bekommen?",
    "Where can I find resources for mental health support on campus?",
    "How do I apply for on-campus housing, and what meal plans are available?",
    "Was muss ich mitbringen, wenn ich meine Masterarbeit anmelden möchte? (Informatik)",
    "Unter welcher Telefonnummer erreiche ich die Studienberatung?",
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
