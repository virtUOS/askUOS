import uuid
import json


def _extract_text_content(content) -> str:
    """Gemini sometimes returns content as [{"text": "..."}] instead of str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content)


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _make_chunk(completion_id: str, created: int, model: str,
                content: str = None, finish_reason: str = None,
                role: str = None) -> str:
    """Build a single SSE chunk in OpenAI format."""
    delta = {}
    if role:
        delta["role"] = role
    if content:
        delta["content"] = content

    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _make_completion(completion_id: str, created: int, model: str,
                     content: str, references: str = "") -> dict:
    """Build a full completion response in OpenAI format."""
    full_content = content
    if references:
        full_content += references

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": full_content,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,  # not tracked
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def _format_references(new_links: list, new_refs: list) -> str:
    """Format references as markdown text."""
    if not new_links and not new_refs:
        return ""

    parts = ["\n\n---\n\n"]
    if new_links:
        parts.append("**References:**\n")
        for link in new_links:
            parts.append(f"- {link}\n")
    if new_refs:
        parts.append("**Documents:**\n")
        for ref in new_refs:
            if isinstance(ref, dict):
                parts.append(f"- {ref.get('source', '')}, p. {ref.get('page', '')}\n")
            else:
                parts.append(f"- {ref}\n")
    return "".join(parts)
