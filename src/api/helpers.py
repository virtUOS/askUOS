import json
import uuid
from urllib.parse import unquote, urlparse

from src.api.translatations import get_translator
from src.chatbot.agents.models import Reference
from src.config.core_config import settings
from src.config.models import VectorDBTypes


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


def _make_chunk(
    completion_id: str,
    created: int,
    model: str,
    content: str = None,
    finish_reason: str = None,
    role: str = None,
) -> str:
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
    if new_refs:
        # TODO: Move to config file
        # reference_url = "https://www.uni-osnabrueck.de/studium/im-studium/zugangs-zulassungs-und-pruefungsordnungen/"
        # TODO move messages to config file
        # parts.append(
        #     _(
        #         "The information provided draws on the documents below that can be found in the [University Website]({}). We encourage you to visit the site to explore these resources for additional details and insights!"
        #     ).format(reference_url)
        # )
        # parts.append("\n\n")

        # Group by source: {"ZPO-GHR.pdf": {"pages": [32, 45], "doc_id": "..."}}
        parts.append(f"**{_('Documents')}:**\n")
        grouped = {}
        for ref in new_refs:
            if isinstance(ref, dict):
                source = ref.get("source", "Unknown")
                page = ref.get("page")
                doc_id = ref.get("doc_id")
            else:
                source = ref.source
                page = ref.page
                doc_id = ref.doc_id

            if source not in grouped:
                grouped[source] = {"pages": [], "doc_id": doc_id}
            if page is not None and page not in grouped[source]["pages"]:
                grouped[source]["pages"].append(page)

        # Build ragflow link template if configured
        ragflow_link = None
        if settings.vector_db_settings.type == VectorDBTypes.INFINITY_RAGFLOW:
            ragflow_link = "{}/document/{}?ext=pdf&prefix=document"

        for source, info in grouped.items():
            pages = sorted(info["pages"])
            doc_id = info["doc_id"]

            if pages:
                page_label = _("Pages") if len(pages) > 1 else _("Page")
                page_list = ", ".join(str(p) for p in pages)
                page_text = f"  **{page_label}**: {page_list}"
            else:
                page_text = ""

            if doc_id and ragflow_link:
                link = ragflow_link.format(
                    settings.vector_db_settings.settings.base_url, doc_id
                )
                parts.append(f"- [{source}]({link}),{page_text}\n")
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
