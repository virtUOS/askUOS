import sys

sys.path.append("/app")

import sys
from typing import List

from src.chatbot.agents.agent_lang_graph import CampusManagementOpenAIToolsAgent

# do not include REPEATED queries or very similar queries (tests will fail)
warm_up_queries = [
    "According to the examination regulations, how are the thesis and oral exam graded?, Mathematics",
    "Wo liegt der NC bei Sport?",
    "hi",
    "who are you",
    "How do I apply for on-campus housing?",
    "Für welche Studiengänge brauche ich ein Latinum?",
    "Wo liegt der NC bei Sport?",
    "Wie viele ECTS-Punkte habe ich in meinem Bachelor (Mathematik)?",
    "Wie viele ECTS-Punkte habe ich in meinem Bachelor (Biologie)?",
    "Muss ich im Grundschullehramt Mathe und Deutsch studieren?",
    "I cannot log into HisInOne, what can I do?",
    "Welche Schnupperangebote bietet die Uni OS?",
    "Kann ich Biologie und Sport auf Lehramt studieren?",
    "What are the application deadlines for the fall and spring semesters for the Computer Science Program?",
    "Was kann ich tun, wenn ich keinen Studienplatz im Master Sport bekommen habe?",
    "Brauche ich für eine Zweitstudienbewerbung in Psychologie den Eignungstest?",
    "Kann ich Politik auf Lehramt studieren?",
    "According to the examination regulations, can I write my Master's thesis in English?, Mathematics",
    "Kann ich Geschichte als Hauptfach studieren?",
    "Welchen NC brauche ich für Psychologie?",
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
