import json
import os
import re
import uuid
from urllib.parse import unquote, urlparse

from src.api.translatations import get_translator
from src.chatbot.agents.models import Reference
from src.config.core_config import settings
from src.config.models import ToolNames, VectorDBTypes


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


def _is_function_call_json(content: str) -> bool:
    """Detect if content is a leaked function/tool call that should not be shown to user.
       Some LLMs fail to return proper structured tool_calls output and instead leak the
       call as plain text — either as JSON (e.g. {"tool_calls": ...}) or as pseudo Python
       call syntax (e.g. ausführen_tool(tool_name='custom_university_web_search',
       tool_arguments={'query': '...'})).
    Args:
        content: The message content to check

    Returns:
        True if content appears to be a leaked function/tool call, False otherwise
    """
    if not content:
        return False

    content_stripped = content.strip()

    # Check for function_call pattern in JSON
    function_call_patterns = [
        r'"function_call"\s*:',
        r'"tool_calls"\s*:',
        # Pseudo Python-call leaks, e.g. some_tool(tool_name='...', tool_arguments={...})
        r"\w+\(\s*tool_name\s*=",
        r"tool_arguments\s*=",
        # Known tool input field names used as kwargs, regardless of the (possibly
        # hallucinated/translated) wrapper function name, e.g. foo(query='...', about_application=True)
        r"\b(query|about_application|teaching_degree|agent_name|task_description|filter_program_name)\s*=\s*['\"{]",
    ]

    for tool_name in ToolNames:
        # Match the tool name however it's quoted: "tool_name", 'tool_name', or bare tool_name(
        escaped = re.escape(tool_name.value)
        function_call_patterns.append(rf"""['"]{escaped}['"]""")
        function_call_patterns.append(rf"\b{escaped}\s*\(")

    for pattern in function_call_patterns:
        if re.search(pattern, content_stripped):
            return True

    # Check if content is valid JSON with function-related keys
    try:
        # Try to parse as JSON
        parsed = json.loads(content_stripped)
        if isinstance(parsed, dict):
            # Check for function call structure
            if "function_call" in parsed or "tool_calls" in parsed:
                return True
            if "name" in parsed and "arguments" in parsed:
                return True
    except (json.JSONDecodeError, ValueError):
        pass

    return False


class StreamingLeakGuard:
    """Guards a token-by-token answer stream against a leaked function/tool
    call blob (see `_is_function_call_json`) reaching the client, while
    preserving live streaming for the overwhelmingly common clean case.

    Only the first `SNIFF_WINDOW_CHARS` characters of the answer are held
    back to check for the leak signature. If they're clean, that buffered
    text is flushed at once and every token after it is passed straight
    through live, exactly as before — the fix only adds a small, fixed
    delay before streaming starts, not a delay proportional to the whole
    answer. If the sniff window looks like a leak, the rest of the answer
    is accumulated silently (never shown), and the caller is expected to
    substitute a fallback message once the stream ends.

    Usage:
        guard = StreamingLeakGuard()
        async for token in some_stream:
            piece = guard.feed(token)
            if piece:
                yield piece
        tail = guard.finalize()
        if tail:
            yield tail
        if guard.leaked:
            # substitute a fallback message; guard.full_answer has the
            # complete (suppressed) text for logging/debugging.
            ...
    """

    SNIFF_WINDOW_CHARS = 60

    def __init__(self):
        self._buffer = ""
        self._sniffing = True
        self.leaked = False
        self.full_answer = ""

    def feed(self, text: str) -> str:
        """Feed a newly-arrived token/chunk. Returns the text (possibly
        empty) that should be yielded to the client right now."""
        if not text:
            return ""
        self.full_answer += text

        if not self._sniffing:
            return "" if self.leaked else text

        self._buffer += text
        if len(self._buffer) < self.SNIFF_WINDOW_CHARS:
            return ""
        return self._resolve_sniff()

    def finalize(self) -> str:
        """Call once the underlying stream has ended. Returns any
        still-buffered text that should be flushed — only relevant if the
        whole answer was shorter than the sniff window and turned out
        clean."""
        if self._sniffing:
            return self._resolve_sniff()
        return ""

    def _resolve_sniff(self) -> str:
        self._sniffing = False
        if _is_function_call_json(self._buffer):
            self.leaked = True
            return ""
        flushed, self._buffer = self._buffer, ""
        return flushed


def _make_chunk(
    completion_id: str,
    created: int,
    model: str,
    content: str = None,
    finish_reason: str = None,
    role: str = None,
    status: str = None,
) -> str:
    """Build a single SSE chunk in OpenAI format.

    `status` is an additive, non-standard field on `delta` used to narrate
    graph progress while a turn is in flight (see
    graph_node_edges.py::_write_status and stream_generator's "custom"
    branch in main.py) -- it's only ever sent on its own chunk, never
    alongside `content`. Any OpenAI-compatible client that only reads
    `delta.content`/`delta.role` (e.g. LibreChat) will just see an
    otherwise-empty delta and ignore it, the same as it already ignores the
    role-announcement chunk sent at the start of every turn.
    """
    delta = {}
    if role:
        delta["role"] = role
    if content:
        delta["content"] = content
    if status:
        delta["status"] = status

    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _make_completion(
    completion_id: str, created: int, model: str, content: str, references: str = ""
) -> dict:
    """Build a full completion response in OpenAI format."""
    full_content = content
    if references:
        full_content += references

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,  # not tracked
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def _format_link(url: str, max_length: int = 60) -> str:
    """Turn a raw URL into a readable markdown link.

    https://www.uni-osnabrueck.de/studium/im-studium/some-very-long-page/
    → [uni-osnabrueck.de/.../some-very-long-page](https://...)
    """
    try:
        parsed = urlparse(url)
        # Remove www. prefix
        domain = parsed.netloc.replace("www.", "")
        # Clean path: remove trailing slash, decode %20 etc.
        path = unquote(parsed.path).strip("/")

        if not path:
            label = domain
        else:
            segments = path.split("/")
            # Last meaningful segment as the page name
            page = segments[-1]
            # Replace hyphens/underscores with spaces for readability
            page_readable = page.replace("-", " ").replace("_", " ")

            if len(segments) > 2:
                label = f"{domain}/.../{page_readable}"
            elif len(segments) == 2:
                label = f"{domain}/{segments[0]}/.../{page_readable}"
            else:
                label = f"{domain}/{page_readable}"

        # Truncate if still too long
        if len(label) > max_length:
            label = label[: max_length - 3] + "..."

        return f"[{label}]({url})"
    except Exception:
        return url


def _format_references(
    new_links: list, new_refs: list[Reference], language: str = "Deutsch"
) -> str:
    """Format references as markdown text."""
    if not new_links and not new_refs:
        return ""

    _ = get_translator(language)
    parts = ["\n\n---\n\n"]

    # ─── Document references ──────────────────────────
    # doc_references — each Reference already carries its own fully-formed
    # link in `url_reference_askuos` (built per-agent in
    # GraphNodesMixin.extract_ragflow_chunks, using that agent's own MCP
    # reference URL)
    if new_refs:
        # Group by source: {"ZPO-GHR.pdf": {"pages": [32, 45], "doc_id": "...", "ragflow_link": "..."}}
        parts.append(f"**{_('Documents')}:**\n")
        grouped = {}
        for ref in new_refs:
            if isinstance(ref, dict):
                source = ref.get(
                    "source", "Unknown"
                )  # document_keyword or doc name in ragflow
                page = ref.get("page")
                doc_id = ref.get("doc_id")
                ragflow_link = ref.get("url_reference_askuos")
            else:
                source = ref.source  # document_keyword
                page = ref.page
                doc_id = ref.doc_id
                ragflow_link = ref.url_reference_askuos

            if source not in grouped:

                grouped[source] = {
                    "pages": [],
                    "doc_id": doc_id,
                    "ragflow_link": ragflow_link,
                }
            if page is not None and page not in grouped[source]["pages"]:
                grouped[source]["pages"].append(page)

        for source, info in grouped.items():
            pages = sorted(info["pages"])
            doc_id = info["doc_id"]
            ragflow_link = info["ragflow_link"]

            if pages:
                page_label = _("Pages") if len(pages) > 1 else _("Page")
                page_list = ", ".join(str(p) for p in pages)
                page_text = f"  **{page_label}**: {page_list}"
            else:
                page_text = ""

            if doc_id and ragflow_link:
                # The link is already complete (built in extract_ragflow_chunks) —
                # no further templating/formatting needed here.
                parts.append(f"- [{source}]({ragflow_link}),{page_text}\n")
            else:
                parts.append(f"- **{source}**,{page_text}\n")

    # ─── Web links ────────────────────────────────────
    if new_links:
        if new_refs:
            parts.append("\n")
        parts.append(f"**{_('Quellen')}:**\n")
        for link in new_links:
            parts.append(f"- {_format_link(link)}\n")

    return "".join(parts)
