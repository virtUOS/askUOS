import csv
import json
import re
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

DATE = "june-2025"
LOGS_DIR = f"evaluation/data/logs_prod/log-{DATE}/log.csv"
SAVE_USER_QUERIES = f"evaluation/data/results/result-{DATE}/user_queries.txt"
FEEDBACK_DATA = f"evaluation/data/results/result-{DATE}/feedback_data.csv"
SAVE_GRAPHS = f"evaluation/data/results/result-{DATE}/"
SAVE_SUMMARY_REPORT = f"evaluation/data/results/result-{DATE}/summary_report.txt"
# Ensure the directory exists


# Read the log file
def read_logs(file_path):
    # Initialize lists to store data
    data = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            try:
                # Skip empty lines
                if not line.strip():
                    continue

                # Split the line by comma, but respect quotes
                parts = []
                current_part = []
                in_quotes = False

                for char in line.strip():
                    if char == '"':
                        in_quotes = not in_quotes
                    elif char == "," and not in_quotes:
                        parts.append("".join(current_part))
                        current_part = []
                    else:
                        current_part.append(char)

                # Add the last part
                if current_part:
                    parts.append("".join(current_part))

                # Debug print for problematic lines
                if len(parts) < 6:
                    print(f"Warning: Line {line_num} has only {len(parts)} parts")
                    print(f"Line content: {line.strip()}")
                    continue

                # Ensure we have exactly 6 parts
                if len(parts) >= 6:
                    # Join any extra parts into the message field
                    message = ",".join(parts[5:])
                    parts = parts[:5] + [message]

                    # Debug print for timestamp format
                    if not re.match(
                        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", parts[0].strip('"')
                    ):
                        print(f"Warning: Invalid timestamp format in line {line_num}")
                        print(f"Timestamp: {parts[0]}")
                        print(f"Full line: {line.strip()}")
                        continue

                    data.append(parts)

            except Exception as e:
                print(f"Error processing line {line_num}: {str(e)}")
                print(f"Line content: {line.strip()}")
                continue

    # Create DataFrame
    df = pd.DataFrame(
        data, columns=["timestamp", "file", "line", "logger", "level", "message"]
    )

    # Clean up the timestamp column - remove any extra quotes
    df["timestamp"] = df["timestamp"].str.strip('"')

    # Convert timestamp to datetime with error handling
    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error converting timestamps: {str(e)}")
        print("First few problematic timestamps:")
        print(df["timestamp"].head())
        raise

    # Clean up other columns - remove any extra quotes
    for col in ["file", "line", "logger", "level", "message"]:
        df[col] = df[col].str.strip('"')

    # Extract various message components
    # 1. User queries
    df["is_user_query"] = df["message"].str.contains("User's query:", na=False)
    df["user_query"] = df["message"].apply(
        lambda x: (
            x.split("User's query: ")[1]
            if isinstance(x, str)
            and "User's query:" in x
            and len(x.split("User's query: ")) > 1
            else None
        )
    )

    # 2. Time taken to start generating answer
    df["time_answer_generation"] = df["message"].apply(
        lambda x: (
            float(
                re.search(r"Time taken to start generating answer: ([\d.]+)", x).group(
                    1
                )
            )
            if isinstance(x, str)
            and "Time taken to start generating answer:" in x
            and re.search(r"Time taken to start generating answer: ([\d.]+)", x)
            else None
        )
    )

    # 3. Time taken to serve whole answer
    df["time_serve_answer"] = df["message"].apply(
        lambda x: (
            float(
                re.search(
                    r"Time taken to serve whole answer to the user: ([\d.]+)", x
                ).group(1)
            )
            if isinstance(x, str)
            and "Time taken to serve whole answer to the user:" in x
            and re.search(r"Time taken to serve whole answer to the user: ([\d.]+)", x)
            else None
        )
    )

    # 4. University website queries
    df["university_website_query"] = df["message"].apply(
        lambda x: (
            x.split("Query used by the University website: ")[1]
            if isinstance(x, str)
            and "Query used by the University website:" in x
            and len(x.split("Query used by the University website: ")) > 1
            else None
        )
    )

    # 5. Search tokens
    df["search_tokens"] = df["message"].apply(
        lambda x: (
            int(re.search(r"Search tokens: (\d+)", x).group(1))
            if isinstance(x, str)
            and "Search tokens:" in x
            and re.search(r"Search tokens: (\d+)", x)
            else None
        )
    )

    # 6. Final output size
    df["final_output_size"] = df["message"].apply(
        lambda x: (
            int(re.search(r"Final output \(search \+ prompt\): (\d+)", x).group(1))
            if isinstance(x, str)
            and "Final output (search + prompt):" in x
            and re.search(r"Final output \(search \+ prompt\): (\d+)", x)
            else None
        )
    )

    # 7. Feedback
    df["is_feedback"] = df["message"].str.contains("Feedback=", na=False)
    df["feedback"] = df["message"].apply(
        lambda x: (
            x.split("Feedback=")[1]
            if isinstance(x, str) and "Feedback=" in x and len(x.split("Feedback=")) > 1
            else None
        )
    )

    # 8. Rate (user satisfaction) - handle both score and rate keys
    df["rate"] = df["message"].apply(
        lambda x: (
            re.search(r'(?:rate|score)": "([^"]+)"', x).group(1)
            if isinstance(x, str)
            and ("rate" in x or "score" in x)
            and re.search(r'(?:rate|score)": "([^"]+)"', x)
            else None
        )
    )

    return df


def save_user_queries(df):
    # Filter for user queries and save to file
    user_queries = df[df["user_query"].notna()]["user_query"].tolist()
    with open(SAVE_USER_QUERIES, "w", encoding="utf-8") as f:
        for query in user_queries:
            f.write(f"{query}\n")


def extract_feedback_to_csv(df):
    # Filter for feedback entries
    feedback_df = df[df["feedback"].notna()].copy()

    # Parse feedback JSON and create columns
    feedback_data = []
    for feedback in feedback_df["feedback"]:
        try:
            # Clean up the feedback string to make it valid JSON
            feedback = feedback.replace("'", '"')
            feedback_dict = json.loads(feedback)

            # Handle both score and rate keys
            if "score" in feedback_dict and "rate" not in feedback_dict:
                feedback_dict["rate"] = feedback_dict.pop("score")

            feedback_data.append(feedback_dict)
        except json.JSONDecodeError:
            print(f"Warning: Could not parse feedback JSON: {feedback}")
            continue

    # Create DataFrame from feedback data
    feedback_df = pd.DataFrame(feedback_data)

    # Save to CSV
    feedback_df.to_csv(FEEDBACK_DATA, index=False)


def analyze_response_times(df):
    # Filter for time taken entries
    time_df = df[df["time_answer_generation"].notna()]

    # Create a box plot of response times
    plt.figure(figsize=(10, 6))
    sns.boxplot(y=time_df["time_answer_generation"])
    plt.title("Distribution of Response Times (Generation)")
    plt.ylabel("Time (seconds)")
    plt.savefig("evaluation/log_evaluation/response_times_generation.png")
    plt.close()

    # Create a box plot of serve times
    time_df = df[df["time_serve_answer"].notna()]
    plt.figure(figsize=(10, 6))
    sns.boxplot(y=time_df["time_serve_answer"])
    plt.title("Distribution of Response Times (Serving)")
    plt.ylabel("Time (seconds)")
    plt.savefig("evaluation/log_evaluation/response_times_serving.png")
    plt.close()


def analyze_user_satisfaction(df):
    # Filter for feedback entries
    feedback_df = df[df["rate"].notna()]

    # Count different rates
    rate_counts = feedback_df["rate"].value_counts()

    # Create a pie chart
    plt.figure(figsize=(8, 8))
    plt.pie(rate_counts.values, labels=rate_counts.index, autopct="%1.1f%%")
    plt.title("User Satisfaction Distribution")
    plt.savefig("evaluation/log_evaluation/user_satisfaction.png")
    plt.close()


def analyze_query_patterns(df):
    # Filter for user queries
    query_df = df[df["user_query"].notna()]

    # Count most common words in queries
    words = " ".join(query_df["user_query"].dropna()).lower().split()
    word_counts = pd.Series(words).value_counts().head(10)

    # Create a bar plot
    plt.figure(figsize=(12, 6))
    word_counts.plot(kind="bar")
    plt.title("Most Common Words in User Queries")
    plt.xlabel("Words")
    plt.ylabel("Count")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{SAVE_GRAPHS}query_patterns.png")
    plt.close()


def analyze_temporal_patterns(df):
    # Add hour to the dataframe
    df["hour"] = df["timestamp"].dt.hour

    # Count queries by hour
    hourly_counts = df[df["is_user_query"]].groupby("hour").size()

    # Create a line plot
    plt.figure(figsize=(12, 6))
    hourly_counts.plot(kind="line", marker="o")
    plt.title("Query Distribution by Hour")
    plt.xlabel("Hour of Day")
    plt.ylabel("Number of Queries")
    plt.grid(True)
    plt.savefig(f"{SAVE_GRAPHS}temporal_patterns.png")
    plt.close()


def generate_summary_stats(df):
    # Calculate summary statistics
    total_queries = df["is_user_query"].sum()
    total_feedback = df["is_feedback"].sum()

    # Debug: Check what we have for time data
    print("Debug info:")
    print(
        f"Total rows with time_answer_generation: {df['time_answer_generation'].notna().sum()}"
    )
    print(f"Total rows with time_serve_answer: {df['time_serve_answer'].notna().sum()}")
    print(
        f"Sample time_answer_generation values: {df['time_answer_generation'].dropna().head().tolist()}"
    )

    # Calculate average times only for non-null values, with better handling
    time_gen_data = df["time_answer_generation"].dropna()
    time_serve_data = df["time_serve_answer"].dropna()

    avg_generation_time = time_gen_data.mean() if len(time_gen_data) > 0 else "No data"
    avg_serve_time = time_serve_data.mean() if len(time_serve_data) > 0 else "No data"

    # Additional time statistics
    if len(time_gen_data) > 0:
        median_generation_time = time_gen_data.median()
        min_generation_time = time_gen_data.min()
        max_generation_time = time_gen_data.max()
        std_generation_time = time_gen_data.std()
    else:
        median_generation_time = min_generation_time = max_generation_time = (
            std_generation_time
        ) = "No data"

    if len(time_serve_data) > 0:
        median_serve_time = time_serve_data.median()
        min_serve_time = time_serve_data.min()
        max_serve_time = time_serve_data.max()
        std_serve_time = time_serve_data.std()
    else:
        median_serve_time = min_serve_time = max_serve_time = std_serve_time = "No data"

    avg_search_tokens = df["search_tokens"].dropna().mean()
    avg_output_size = df["final_output_size"].dropna().mean()

    # Additional token and output statistics
    search_tokens_data = df["search_tokens"].dropna()
    output_size_data = df["final_output_size"].dropna()

    median_search_tokens = (
        search_tokens_data.median() if len(search_tokens_data) > 0 else "No data"
    )
    median_output_size = (
        output_size_data.median() if len(output_size_data) > 0 else "No data"
    )

    # Query frequency analysis
    df_with_time = df.copy()
    df_with_time["date"] = df_with_time["timestamp"].dt.date
    daily_queries = df_with_time[df_with_time["is_user_query"]].groupby("date").size()
    avg_daily_queries = daily_queries.mean() if len(daily_queries) > 0 else 0

    # Peak usage analysis
    df_with_time["hour"] = df_with_time["timestamp"].dt.hour
    hourly_queries = df_with_time[df_with_time["is_user_query"]].groupby("hour").size()
    peak_hour = hourly_queries.idxmax() if len(hourly_queries) > 0 else "No data"
    peak_hour_count = hourly_queries.max() if len(hourly_queries) > 0 else 0

    # Create a summary report
    with open(SAVE_SUMMARY_REPORT, "w") as f:
        f.write("Chatbot Usage Summary Report\n")
        f.write("==========================\n\n")

        # Basic metrics
        f.write("BASIC METRICS\n")
        f.write("-------------\n")
        f.write(f"Total number of queries: {total_queries}\n")
        f.write(f"Total feedback received: {total_feedback}\n")
        f.write(
            f"Feedback rate: {(total_feedback/total_queries*100):.1f}%\n"
            if total_queries > 0
            else "Feedback rate: No queries\n"
        )
        f.write(f"Average daily queries: {avg_daily_queries:.1f}\n")
        f.write(f"Peak usage hour: {peak_hour} ({peak_hour_count} queries)\n")
        f.write("\n")

        # Performance metrics
        f.write("PERFORMANCE METRICS\n")
        f.write("-------------------\n")
        if isinstance(avg_generation_time, str):
            f.write(f"Answer generation time: {avg_generation_time}\n")
        else:
            f.write(
                f"Average answer generation time: {avg_generation_time:.2f} seconds\n"
            )
            f.write(
                f"Median answer generation time: {median_generation_time:.2f} seconds\n"
            )
            f.write(
                f"Min/Max generation time: {min_generation_time:.2f}/{max_generation_time:.2f} seconds\n"
            )
            f.write(f"Std dev generation time: {std_generation_time:.2f} seconds\n")

        if isinstance(avg_serve_time, str):
            f.write(f"Answer serving time: {avg_serve_time}\n")
        else:
            f.write(f"Average answer serving time: {avg_serve_time:.2f} seconds\n")
            f.write(f"Median answer serving time: {median_serve_time:.2f} seconds\n")
            f.write(
                f"Min/Max serving time: {min_serve_time:.2f}/{max_serve_time:.2f} seconds\n"
            )
            f.write(f"Std dev serving time: {std_serve_time:.2f} seconds\n")
        f.write("\n")

        # Resource usage
        f.write("RESOURCE USAGE\n")
        f.write("--------------\n")
        f.write(f"Average search tokens: {avg_search_tokens:.2f}\n")
        f.write(f"Median search tokens: {median_search_tokens:.2f}\n")
        f.write(f"Average output size: {avg_output_size:.2f}\n")
        f.write(f"Median output size: {median_output_size:.2f}\n")
        f.write("\n")

        # User satisfaction
        f.write("USER SATISFACTION\n")
        f.write("-----------------\n")

        # Read feedback data from CSV if it exists
        try:
            feedback_csv_df = pd.read_csv(FEEDBACK_DATA)
            if len(feedback_csv_df) > 0 and "rate" in feedback_csv_df.columns:
                rate_counts = feedback_csv_df["rate"].value_counts()
                total_feedback_csv = len(feedback_csv_df)

                for rate, count in rate_counts.items():
                    percentage = (count / total_feedback_csv) * 100
                    f.write(f"{rate}: {count} ({percentage:.1f}%)\n")

                # Calculate average satisfaction score using emoji mapping
                satisfaction_mapping = {
                    "😞": 1,
                    "🙁": 2,
                    "😐": 3,
                    "🙂": 4,
                    "😀": 5,
                }

                numeric_ratings = []
                for rate in feedback_csv_df["rate"]:
                    if pd.notna(rate) and rate in satisfaction_mapping:
                        numeric_ratings.append(satisfaction_mapping[rate])

                if numeric_ratings:
                    avg_satisfaction = sum(numeric_ratings) / len(numeric_ratings)
                    f.write(
                        f"\nAverage satisfaction score: {avg_satisfaction:.2f}/5.0\n"
                    )

                    # Add distribution summary
                    positive_feedback = sum(1 for r in numeric_ratings if r >= 4)
                    neutral_feedback = sum(1 for r in numeric_ratings if r == 3)
                    negative_feedback = sum(1 for r in numeric_ratings if r <= 2)

                    f.write(
                        f"Positive feedback (😀🙂): {positive_feedback} ({positive_feedback/len(numeric_ratings)*100:.1f}%)\n"
                    )
                    f.write(
                        f"Neutral feedback (😐): {neutral_feedback} ({neutral_feedback/len(numeric_ratings)*100:.1f}%)\n"
                    )
                    f.write(
                        f"Negative feedback (🙁😞): {negative_feedback} ({negative_feedback/len(numeric_ratings)*100:.1f}%)\n"
                    )
                else:
                    f.write("No valid satisfaction ratings found\n")
            else:
                f.write("No feedback data available in CSV\n")
        except FileNotFoundError:
            f.write("No feedback data available\n")
        except Exception as e:
            f.write(f"Error reading feedback data: {str(e)}\n")


def main():
    # Read the logs
    df = read_logs(LOGS_DIR)

    # Save user queries
    save_user_queries(df)

    # Extract feedback to CSV
    extract_feedback_to_csv(df)

    # Generate various analyses
    analyze_response_times(df)
    analyze_user_satisfaction(df)
    analyze_query_patterns(df)
    analyze_temporal_patterns(df)
    generate_summary_stats(df)

    print("Analysis complete! Check the evaluation directory for generated files.")


if __name__ == "__main__":
    main()
