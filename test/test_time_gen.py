from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
import time
import numpy as np
from typing import List, Tuple


queries = [
    "What are the admission requirements for undergraduate programs?",
    "Can I apply for multiple programs at the same time?",
    "What is the deadline for submitting my application?",
    # "Are there any scholarships available for international students?",
    # "How do I submit my transcripts with my application?",
    # "What standardized tests are required for admission?",
    # "Can I check the status of my application online?",
    # "What is the tuition fee structure for the upcoming academic year?",
    # "Is there a separate application process for financial aid?",
    # "What documents do I need to include with my application?",
    # "Are interviews required for the application process?",
    # "What happens if I miss the application deadline?",
    # "How can I contact the admissions office for further questions?",
    # "Are there any specific prerequisites for my chosen major?",
    # "What resources are available to help with application essays?",
    # "Can I defer my application to the next academic year?",
    # "How can I access my course materials online?",
    # "Where do I find information about campus events?",
    # "What are the deadlines for course registration?",
    # "How do I connect with my academic advisor?",
    # "Where can I find tutoring services on campus?",
    # "What health services are available for students?",
    # "How can I join a student organization or club?",
    # "Where can I find job or internship opportunities?",
    # "How do I check my grades online?",
    # "What should I do if I need to take a leave of absence?",
    # "Are there resources for mental health support?",
    # "How can I get involved in research opportunities?",
    # "What are my options for studying abroad?",
    # "How do I apply for graduation?",
    # "What sports facilities are available to students?",
]


warm_up_queries = [
    "Hello! How can I get started with my application?",
    # "What programs does your university offer?",
    # "Can you tell me about campus facilities?",
    # "What is the student-to-faculty ratio?",
    # "How do I reset my university account password?",
]


agent_executor = CampusManagementOpenAIToolsAgent.run()


def measure_response_time_advanced(
    queries: List[str], warm_up_queries: List[str]
) -> Tuple[float, float, List[float]]:
    """
    Measures the response time of executing a series of queries.

    This function first performs a warm-up phase by executing a set of warm-up queries.
    Then, it measures the response time for each query in the
    `queries` list, sleeping for 2 seconds between each query. It returns the average
    response time, the standard deviation of the response times, and the list of individual
    response times.

    Args:
        queries (list): A list of queries to be executed and timed.
        warm_up_queries (list): A list of warm-up queries to be executed before timing the main queries.

    Returns:
        tuple: A tuple containing:
            - average_time (float): The average response time of the queries.
            - std_dev (float): The standard deviation of the response times.
            - times (list): A list of individual response times for each query.
    """
    times = []

    # Warm-up phase
    for q in warm_up_queries:
        agent_executor(q)  # Execute warm-up queries, timing not recorded

    for q in queries:
        start_time = time.time()
        agent_executor(q)
        end_time = time.time()
        times.append(end_time - start_time)
        time.sleep(2)  # Sleep for 1 second between queries

    average_time = np.mean(times)
    std_dev = np.std(times)

    return average_time, std_dev, times


if __name__ == "__main__":
    average_time, std_dev, times = measure_response_time_advanced(
        queries, warm_up_queries
    )
    print(f"Average response time: {average_time} seconds")
    print(f"Standard deviation: {std_dev} seconds")
    print(f"Individual response times: {times}")
