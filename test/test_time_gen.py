from src.chatbot.agents.agent_openai_tools import CampusManagementOpenAIToolsAgent
import time
import numpy as np
from typing import List, Tuple
from src.config.core_config import settings
from plot_tests import plot_result


queries = [
    "What are the admission requirements for undergraduate programs?",
    "Can I apply for multiple programs at the same time?",
    "What is the deadline for submitting my application?",
    "Are there any scholarships available for international students?",
    "How do I submit my transcripts with my application?",
    "What standardized tests are required for admission?",
    "Can I check the status of my application online?",
    "What is the tuition fee structure for the upcoming academic year?",
    "Is there a separate application process for financial aid?",
    "What documents do I need to include with my application?",
    "Are interviews required for the application process?",
    "What happens if I miss the application deadline?",
    "How can I contact the admissions office for further questions?",
    "Are there any specific prerequisites for my chosen major?",
    "What resources are available to help with application essays?",
    "Can I defer my application to the next academic year?",
    "How can I access my course materials online?",
    "Where do I find information about campus events?",
    "What are the deadlines for course registration?",
    "How do I connect with my academic advisor?",
    "Where can I find tutoring services on campus?",
    "What health services are available for students?",
    "How can I join a student organization or club?",
    "Where can I find job or internship opportunities?",
    "How do I check my grades online?",
    "What should I do if I need to take a leave of absence?",
    "Are there resources for mental health support?",
    "How can I get involved in research opportunities?",
    "What are my options for studying abroad?",
    "How do I apply for graduation?",
    "What sports facilities are available to students?",
]


warm_up_queries = [
    "Hello! How can I get started with my application?",
    "What programs does your university offer?",
    "Can you tell me about campus facilities?",
    "What is the student-to-faculty ratio?",
    "How do I reset my university account password?",
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
        settings.time_request_sent = start_time
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
    print(f"Average (whole)response time: {average_time} seconds")
    print(f"Standard deviation (whole response): {std_dev} seconds")
    print(f"Individual (whole)response times: {times}")

    # Generate plots
    plot_result(
        times,
        filename="response_times.png",
        title="Response Times",
        x_label="Index",
        y_label="Time",
    )

    average_time_first_stream = np.mean(settings.total_time_first_stream)
    std_dev_first_stream = np.std(settings.total_time_first_stream)
    print(f"Average (first stream)response time: {average_time_first_stream} seconds")
    print(f"Standard deviation (first stream response): {std_dev_first_stream} seconds")
    print(
        f"Individual (first stream)response times: {settings.total_time_first_stream}"
    )

    # Generate plots
    plot_result(
        settings.total_time_first_stream,
        filename="response_times_first_stream.png",
        title="Response Times (First Stream)",
        x_label="Index",
        y_label="Time",
    )

    average_total_tokens = np.mean(settings.final_output_tokens)
    std_dev_total_tokens = np.std(settings.final_output_tokens)
    print(f"Average (total)response tokens: {average_total_tokens}")
    print(f"Standard deviation (total response tokens): {std_dev_total_tokens}")
    print(f"Individual (total)response tokens: {settings.final_output_tokens}")

    # Generate plots
    plot_result(
        settings.final_output_tokens,
        filename="response_tokens.png",
        title="Response Tokens",
        x_label="Index",
        y_label="Tokens",
    )

    average_search_tokens = np.mean(settings.final_search_tokens)
    std_dev_search_tokens = np.std(settings.final_search_tokens)
    print(f"Average (search)response tokens: {average_search_tokens}")
    print(f"Standard deviation (search response tokens): {std_dev_search_tokens}")
    print(f"Individual (search)response tokens: {settings.final_search_tokens}")

    # Generate plots
    plot_result(
        settings.final_search_tokens,
        filename="search_tokens.png",
        title="Search Tokens",
        x_label="Index",
        y_label="Tokens",
    )
