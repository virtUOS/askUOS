import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field

import requests

# from tests.warm_up import warm_up_queries
# QUERIES = warm_up_queries

API_URL = "http://localhost:8000"
API_KEY = askUOS_API_KEY = os.getenv("STREAMLIT_API_KEY", "")
headers = {
    "Authorization": f"Bearer {askUOS_API_KEY}",
}

# Each user gets a different set of queries to make history more interesting
USER_QUERIES = [
    [
        "What are the admission requirements for bachelor bioloy?",
        "What documents do I need to apply?",
        # "When is the application deadline?",
    ],
    [
        "How do I apply for a student visa?",
        "How long does the visa process take?",
        # "What are the visa fees?",
    ],
    [
        "What courses are available in computer science?",
        "Is there a master's program in AI?",
        # "What are the tuition fees?",
    ],
    [
        "Where is the international office?",
        "How do I get a student ID?",
        # "What sports facilities are available?",
    ],
    [
        "What scholarships are available?",
        "How do I apply for financial aid?",
        # "Is there on-campus housing?",
    ],
]


@dataclass
class UserResult:
    user_id: str
    thread_id: str
    queries: list[str]
    durations: list[float] = field(default_factory=list)
    streamed_responses: list[str] = field(default_factory=list)
    history_ok: bool = False
    errors: list[str] = field(default_factory=list)


def consume_stream(response: requests.Response) -> str:
    """Consume stream and return the full assembled text."""
    full_text = ""
    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
        if decoded == "data: [DONE]":
            break
        if decoded.startswith("data: "):
            try:
                chunk = json.loads(decoded[len("data: ") :])
                delta = (
                    chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                )
                if delta:
                    full_text += delta
            except json.JSONDecodeError:
                continue
    return full_text


def run_user_session(result: UserResult):

    for query in result.queries:
        start = time.time()
        try:
            response = requests.post(
                f"{API_URL}/v1/chat/completions",
                headers=headers,
                json={
                    "messages": [{"role": "user", "content": query}],
                    "thread_id": result.thread_id,
                    "stream": True,
                    "keep_user_message_history": True,  #  required
                    "language": "English",
                },
                stream=True,  #  do not buffer
                timeout=120,
            )
            response.raise_for_status()
            text = consume_stream(response)
            result.streamed_responses.append(text)

        except Exception as e:
            result.errors.append(f"Stream error on '{query}': {e}")
            result.streamed_responses.append("")
        finally:
            result.durations.append(round(time.time() - start, 2))


def verify_history(result: UserResult):
    """Run after all threads complete."""

    try:
        response = requests.get(
            f"{API_URL}/v1/threads/{result.thread_id}/messages",
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        messages = response.json().get("messages", [])

        user_msgs = [m.get("content") for m in messages if m.get("role") == "user"]
        assistant_msgs = [
            m.get("content") for m in messages if m.get("role") == "assistant"
        ]

        missing_user = [q for q in result.queries if q not in user_msgs]
        missing_assistant_msgs = [
            q for q in result.streamed_responses if q not in assistant_msgs
        ]
        missing_assistant = len(assistant_msgs) < len(result.queries)

        result.history_ok = not missing_user and not missing_assistant

        if missing_user:
            result.errors.append(f"Missing user messages in history: {missing_user}")
        if missing_assistant:
            result.errors.append(
                f"Expected {len(result.queries)} assistant messages, got {len(assistant_msgs)}"
            )
        if missing_assistant_msgs:
            result.errors.append(
                f"Assitant messages are not container in retrieved history. Expected messages: {missing_assistant_msgs}"
            )
    except Exception as e:
        result.errors.append(f"History fetch error: {e}")


def test_concurrent_streaming_users():
    results = [
        UserResult(
            user_id=f"user_{i + 1}",
            thread_id=str(uuid.uuid4()),
            queries=USER_QUERIES[i],
        )
        for i in range(5)
    ]

    threads = [threading.Thread(target=run_user_session, args=(r,)) for r in results]

    overall_start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    overall_duration = round(time.time() - overall_start, 2)

    # ── Verify all histories AFTER all threads complete ──────────────
    print("\nVerifying histories...")
    for result in results:
        verify_history(result)

    # ── Stats ────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"{'CONCURRENT STREAMING USER TEST RESULTS':^65}")
    print("=" * 65)

    total_errors = 0
    for r in results:
        avg = round(sum(r.durations) / len(r.durations), 2) if r.durations else 0
        status = "✅" if not r.errors else "❌"
        history = "✅" if r.history_ok else "❌"
        total_errors += len(r.errors)

        print(f"\n[{r.user_id}] thread: {r.thread_id[:8]}...")
        print(f"  History correct  : {history}")
        print(f"  Status           : {status}")
        if r.errors:
            for err in r.errors:
                print(f"  ⚠ {err}")
        print(f"  Queries sent     : {len(r.queries)}")
        print(f"  Per query (s)    : {list(zip(r.queries, r.durations))}")
        print(f"  Avg per query    : {avg}s")
        print(f"  Slowest query    : {max(r.durations)}s")
        print(f"  Fastest query    : {min(r.durations)}s")

    print("\n" + "-" * 65)
    print(f"  Total users          : {len(results)}")
    print(f"  Total queries sent   : {sum(len(r.queries) for r in results)}")
    print(f"  Total errors         : {total_errors}")
    print(
        f"  All histories OK     : {'✅' if all(r.history_ok for r in results) else '❌'}"
    )
    print(f"  Total wall time      : {overall_duration}s")
    print("=" * 65)


if __name__ == "__main__":
    test_concurrent_streaming_users()
