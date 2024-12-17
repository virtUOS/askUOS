from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
from typing import List


warm_up_queries = [
    "Hello! How can I get started with my application?",
    "How do I reset my university account password?",
]


agent_executor = CampusManagementOpenAIToolsAgent.run()


def warm_up_agent(warm_up_queries: List[str]) -> None:
    """
    Downloads models and  prepare the agent for actual tasks.

    Parameters:
    warm_up_queries (List[str]): A list of queries to be executed during the warm-up phase.

    Returns:
    None
    """

    # Warm-up phase
    for q in warm_up_queries:
        agent_executor(q)  # Execute warm-up queries, timing not recorded


if __name__ == "__main__":

    warm_up_agent(warm_up_queries)
