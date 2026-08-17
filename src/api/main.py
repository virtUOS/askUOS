import sys

sys.path.append("/app")
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Set

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import Overwrite

from src.api.dependencies import get_agent
from src.api.helpers import (
    StreamingLeakGuard,
    _completion_id,
    _extract_text_content,
    _format_references,
    _is_function_call_json,
    _make_chunk,
    _make_completion,
)
from src.api.models import ChatCompletionRequest, ChatRequest, Message
from src.api.translatations import _get_error_messages
from src.chatbot.agents.graph import CampusManagementAgent
from src.chatbot.agents.subagents.main import subagents_registry
from src.chatbot.db.redis_pool import redis_client
from src.chatbot.prompt.prompt_date import get_current_date
from src.chatbot.tools.utils.exceptions import ProgrammableSearchException
from src.chatbot_log.chatbot_logger import bind_request_context, log_event, logger
from src.config.core_config import settings
from src.config.models import Languages


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: Move intizialization of singletons and settings here
    await redis_client.initialize()

    # Initialize agents if mcps were provided !! subagents must be initialized first
    if settings.mcp_agents:
        # await subagents_registry.create_subagents()
        await subagents_registry.create_mcp_clients()
    # Startup: eagerly initialize the singleton so the first request isn't slow
    agent = CampusManagementAgent()
    await agent._ensure_async_initialized()
    app.state.agent = agent
    yield
    # Shutdown: clean up Redis connection
    await agent.cleanup()
    await redis_client.cleanup()


# TODO: Refactor key management (should be more robust)
# Load valid keys.
#
# Two deliberately separate scopes, backed by two disjoint env vars:
# - API_KEYS: gates /v1/chat/completions. These may be handed out broadly
#   (e.g. to external LibreChat-compatible integrations calling in over the
#   public internet)
# - HISTORY_API_KEYS: gates /v1/threads/* (get_messages/delete_messages,
#   i.e. reading or wiping any user's conversation history). Kept as a
#   separate set of secrets on purpose: a completions-only API key must not
#   also be able to read or delete someone else's chat history just because
#   it happens to be a valid Bearer token somewhere in this API. There is no
#   per-user scoping within HISTORY_API_KEYS itself (any key in this set can
#   still read/delete any thread_id) — this only separates "can chat" from
#   "can read/wipe history," it doesn't yet scope a key to one user's own
#   threads.
_valid_api_keys: Set[str] = set(
    key.strip() for key in os.getenv("API_KEYS", "").split(",") if key.strip()
)
_valid_history_api_keys: Set[str] = set(
    key.strip() for key in os.getenv("HISTORY_API_KEYS", "").split(",") if key.strip()
)

_security = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> str:
    """Validate the Bearer token for /v1/chat/completions against API_KEYS."""
    if credentials.credentials not in _valid_api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return credentials.credentials


async def verify_history_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> str:
    """Validate the Bearer token for /v1/threads/* against HISTORY_API_KEYS
    — intentionally a different key set than verify_api_key (see the note
    above _valid_api_keys)."""
    if credentials.credentials not in _valid_history_api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return credentials.credentials


app = FastAPI(lifespan=lifespan, title="askUOS API")

# CORS is only relevant for browser-based clients calling this API
# cross-origin (e.g. ui-react running on its own dev server/port, or a chat
# widget embedded on a different domain) — server-to-server callers (curl,
# another backend, an external LibreChat-compatible integration) are never
# affected by CORS, since it's a browser-only enforcement mechanism. No
# middleware is added at all unless at least one origin is configured via
# application.cors_allowed_origins in backend_config.yaml, so this is a
# no-op for deployments that don't need it.
if settings.application.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.application.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: str = Security(verify_api_key),
    agent: CampusManagementAgent = Depends(get_agent),  # inject dependencies
):
    """
    curl -X POST http://localhost:8000/v1/chat/completions \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer sk-askUOS-abc123" \
        -d '{
        "model": "askUOS-agent",
        "messages": [{"role": "user", "content": "According to the examination regulations, can I write a master thesis in english (Biology)? (answer shortly)"}],
        "stream": true,
        "thread_id": "test-123",
        "language": "Deutsch"
    }'   --no-buffer

  curl -X POST http://localhost:8000/v1/chat/completions \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer sk-askUOS-abc123" \
        -d '{
            "model": "askUOS-agent",
            "messages": [{"role": "user", "content": "Can I study math? (answer shortly)"}],
            "stream": true
        }'   --no-buffer
    """

    language = request.language or Languages.GERMAN
    keep_user_message_history = request.keep_user_message_history
    error_messages = _get_error_messages(language)
    # Fresh thread_id if non provided (this means that the client sends all chat history e.g., Librechat)
    thread_id = request.thread_id if request.thread_id else str(uuid.uuid4())

    # Bind thread_id so every log line for this request — across main.py and
    # the graph nodes — carries it automatically, without passing it through
    # every call site by hand. request_id is bound below once completion_id
    # is known.
    bind_request_context(thread_id=thread_id)
    turn_start = time.monotonic()

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.application.recursion_limit,
    }

    # Convert LibreChat's full history into LangChain messages
    langchain_messages = []
    for msg in request.messages:
        if msg.role == "user":
            langchain_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            langchain_messages.append(AIMessage(content=msg.content))
        # system messages are built in agent_node, skip them

    # Only the last user message drives the agent
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )

    input_data = {
        # Pass full history — gives the LLM conversation context (if provided by the client)
        "messages": langchain_messages,
        "user_initial_query": user_message,
        "current_date": get_current_date("deutsch"),
        "language": language,
        "visited_links": [],
        "doc_references": [],
        "about_application": False,
        "teaching_degree": False,
        "rewrite_query": False,
    }

    completion_id = _completion_id()
    created = int(time.time())
    model = request.model
    bind_request_context(request_id=completion_id)

    # Snapshot previous references
    prev_state = await agent._graph.aget_state(config)
    if prev_state.values:
        prev_links_count = len(prev_state.values.get("visited_links", []))
        prev_refs_count = len(prev_state.values.get("doc_references", []))
    else:
        prev_links_count = 0
        prev_refs_count = 0

    async def _save_to_chat_history(_content: str):
        if keep_user_message_history:
            await agent._graph.aupdate_state(
                config,
                {
                    "user_message_history": [
                        {"role": "user", "content": user_message},
                        {
                            "role": "assistant",
                            "content": _content,
                        },
                    ]
                },
            )

    # ─── Streaming ─────────────────────────────────────

    if request.stream:

        async def stream_generator():
            streamed = False
            error = None
            ai_answer = ""
            refs_text = ""

            # Role chunk (first chunk announces the role)
            yield _make_chunk(completion_id, created, model, role="assistant")

            try:
                ai_answer = ""
                # Guards against the model leaking a function-call JSON/
                # pseudo-call blob as its "final answer" text (seen from the
                # generate-family nodes, which have no tools bound at all for
                # this call). Only the first ~60 chars are held back to
                # check; if clean — the overwhelming common case — every
                # token after that streams live exactly as before.
                leak_guard = StreamingLeakGuard()
                # "custom" carries progress narration emitted via
                # get_stream_writer() from graph nodes (see
                # graph_node_edges.py::_write_status) — agent_node's tool
                # decision, tool_node's web crawl/MCP subagent calls,
                # judge_node, grade_documents, and rewrite are otherwise
                # silent dead time, since only the generate*/
                # generate_application/generate_teaching_degree_node nodes
                # ever stream real answer content below. With stream_mode as
                # a list, each item is (mode_name, payload) instead of the
                # bare (msg, metadata) tuple stream_mode="messages" alone
                # would yield.
                async for stream_mode_name, payload in agent._graph.astream(
                    input_data,
                    config=config,
                    stream_mode=["messages", "custom"],
                ):
                    if stream_mode_name == "custom":
                        # Not answer content — bypasses the leak guard
                        # entirely and is never saved to chat history.
                        status = (
                            payload.get("status") if isinstance(payload, dict) else None
                        )
                        if status:
                            yield _make_chunk(
                                completion_id, created, model, status=status
                            )
                        continue

                    msg, metadata = payload
                    if (
                        msg.content
                        and not isinstance(msg, HumanMessage)
                        and not isinstance(msg, ToolMessage)
                        and (
                            metadata["langgraph_node"] == "generate"
                            or metadata["langgraph_node"] == "generate_application"
                            or metadata["langgraph_node"]
                            == "generate_teaching_degree_node"
                        )
                    ):
                        text = _extract_text_content(msg.content)
                        if text:
                            to_yield = leak_guard.feed(text)
                            if to_yield:
                                streamed = True
                                yield _make_chunk(
                                    completion_id, created, model, content=to_yield
                                )

                tail = leak_guard.finalize()
                if tail:
                    streamed = True
                    yield _make_chunk(completion_id, created, model, content=tail)

                ai_answer = leak_guard.full_answer
                if leak_guard.leaked:
                    log_event(
                        "FUNCTION_CALL_LEAK",
                        "Detected and suppressed a leaked function-call blob in "
                        "streamed generate-node output",
                        endpoint="chat_completions",
                        query=user_message,
                        content_preview=ai_answer[:120],
                    )
                    ai_answer = error_messages["generic"]
                    streamed = True
                    yield _make_chunk(completion_id, created, model, content=ai_answer)

                # Stream references
                final_state = await agent._graph.aget_state(config)
                values = final_state.values
                new_links = list(
                    set(values.get("visited_links", [])[prev_links_count:])
                )
                new_refs = values.get("doc_references", [])[prev_refs_count:]
                refs_text = _format_references(new_links, new_refs, language)
                # if both answer and sources exist
                if refs_text and ai_answer:
                    yield _make_chunk(completion_id, created, model, content=refs_text)

                    content_ref = ai_answer + refs_text
                    await _save_to_chat_history(content_ref)
                    streamed = True
                    if len(ai_answer) < 5:
                        logger.warning(
                            f"[AI-ANSWER-TOO-SHORT] AI answer too short: Answer: {ai_answer}"
                        )
                # if an answer could not be generated but some sources were found
                elif refs_text and not ai_answer:
                    _only_ref_content = (
                        error_messages["generic_with_references"] + refs_text
                    )
                    yield _make_chunk(
                        completion_id, created, model, content=_only_ref_content
                    )
                    content_ref = _only_ref_content + refs_text
                    await _save_to_chat_history(content_ref)
                    streamed = True
                    logger.warning(
                        "[ONLY_REFERENCE_ANSWER] Failed to provide an answer. Only sources were provided"
                    )
                # if an answer was generated without references
                elif streamed and ai_answer:
                    await _save_to_chat_history(ai_answer)
                    if len(ai_answer) < 5:
                        logger.warning(
                            f"[AI-ANSWER-TOO-SHORT] AI answer too short: Answer: {ai_answer}"
                        )

                # Direct response (no tools used)
                if not streamed:
                    # Reuse final_state (fetched above) instead of a second
                    # aget_state round-trip — nothing changes it in between.
                    content = _extract_text_content(values["messages"][-1].content)
                    if not content:
                        raise ValueError(
                            f"[API] Agent Node Failed to generate content or there was no content to stream. Query {user_message}"
                        )

                    if _is_function_call_json(content):
                        # Check if content is a function call JSON that should not be shown
                        log_event(
                            "FUNCTION_CALL_LEAK",
                            "Detected and suppressed a leaked function-call blob in "
                            "chat_completions direct (no-tool) response",
                            endpoint="chat_completions_direct",
                            query=user_message,
                            content_preview=content[:120],
                        )
                        content = error_messages["generic"]

                    yield _make_chunk(completion_id, created, model, content=content)
                    ai_answer = content
                    await _save_to_chat_history(content)

            except GraphRecursionError:
                # No separate warning log here — the TURN_COMPLETED event
                # below already records error="recursion" for every such
                # turn, so a free-text line would just duplicate that.
                error = "recursion"
                content = error_messages["recursion"]
                yield _make_chunk(
                    completion_id,
                    created,
                    model,
                    content=content,
                )
                await _save_to_chat_history(content)

            except ProgrammableSearchException:
                # Same as above — TURN_COMPLETED already records
                # error="search_error"; no need to log it a second time.
                error = "search_error"
                content = error_messages["search_error"]
                yield _make_chunk(
                    completion_id,
                    created,
                    model,
                    content=content,
                )
                await _save_to_chat_history(content)

            except Exception as e:
                error = "unexpected_error"
                logger.exception(f"[ERROR] Unexpected error processing query: {e}")
                content = error_messages["generic"]
                yield _make_chunk(
                    completion_id,
                    created,
                    model,
                    content=content,
                )
                await _save_to_chat_history(content)

            # Final chunk with finish_reason
            yield _make_chunk(completion_id, created, model, finish_reason="stop")
            yield "data: [DONE]\n\n"

            # One canonical, structured event per completed turn — covers
            # most "what happened for this user's question" analysis without
            # having to reconstruct it from scattered debug lines.
            log_event(
                "TURN_COMPLETED",
                "Chat turn completed",
                query=user_message,
                language=str(language),
                has_references=refs_text or "",
                ai_answer=ai_answer,
                error=error,
                latency_ms=round((time.monotonic() - turn_start) * 1000, 1),
            )

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ─── Non-streaming ─────────────────────────────────

    error = None
    try:
        result = await agent._graph.ainvoke(input_data, config=config)
        content = _extract_text_content(result["messages"][-1].content)

        if not content:
            raise ValueError(
                f"[API] Agent Node Failed to generate content. Query {user_message}"
            )
        # Check if content is a function call JSON that should not be shown
        if _is_function_call_json(content):
            log_event(
                "FUNCTION_CALL_LEAK",
                "Detected and suppressed a leaked function-call blob in "
                "non-streaming chat_completions response",
                endpoint="chat_completions_non_streaming",
                query=user_message,
                content_preview=content[:120],
            )
            content = error_messages["generic"]

        new_links = list(set(result.get("visited_links", [])[prev_links_count:]))
        new_refs = result.get("doc_references", [])[prev_refs_count:]
        refs_text = _format_references(new_links, new_refs, language)
    except GraphRecursionError:
        # No separate warning log here — the TURN_COMPLETED event below
        # already records error="recursion" for every such turn, so a
        # free-text line would just duplicate that.
        error = "recursion"
        content = error_messages["recursion"]
        refs_text = ""

    except ProgrammableSearchException:
        # Same as above — TURN_COMPLETED already records
        # error="search_error"; no need to log it a second time.
        error = "search_error"
        content = error_messages["search_error"]
        refs_text = ""

    except Exception as e:
        error = "unexpected_error"
        logger.exception(f"[ERROR] Unexpected error processing query: {e}")
        content = error_messages["generic"]
        refs_text = ""

    log_event(
        "TURN_COMPLETED",
        "Chat turn completed",
        query=user_message,
        language=str(language),
        streaming=False,
        has_references=bool(refs_text),
        ai_answer=content or "",
        error=error,
        latency_ms=round((time.monotonic() - turn_start) * 1000, 1),
    )

    return JSONResponse(
        _make_completion(completion_id, created, model, content, refs_text)
    )


# Gated by its own key set (HISTORY_API_KEYS via verify_history_api_key),
# deliberately separate from the /v1/chat/completions key set (API_KEYS) —
# a completions-only key must not also grant read/delete access to a user's
# conversation history.
@app.get("/v1/threads/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    api_key: str = Security(verify_history_api_key),
    agent: CampusManagementAgent = Depends(get_agent),
):
    config = {"configurable": {"thread_id": thread_id}}
    state = await agent._graph.aget_state(config)
    if not state.values:
        return {"messages": []}

    messages = state.values.get("user_message_history", [])

    return {"messages": messages}


# Gated by HISTORY_API_KEYS via verify_history_api_key — see the identical
# note above get_messages().
@app.delete("/v1/threads/{thread_id}/messages")
async def delete_messages(
    thread_id: str,
    api_key: str = Security(verify_history_api_key),
    agent: CampusManagementAgent = Depends(get_agent),
):
    config = {"configurable": {"thread_id": thread_id}}

    await agent._graph.aupdate_state(
        config,
        {
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)],
            # Bypass the reducer and replace the entire messages list
            "user_message_history": Overwrite([]),
        },
    )

    return {"deleted": True}


# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
