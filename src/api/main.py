import sys

sys.path.append("/app")
import asyncio
import contextlib
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Set

import redis.asyncio as redis
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
from src.api.models import CancelRequest, ChatCompletionRequest, ChatRequest, Message
from src.api.translatations import _get_error_messages
from src.chatbot.agents.graph import CampusManagementAgent
from src.chatbot.agents.subagents.main import subagents_registry
from src.chatbot.db.redis_pool import redis_client
from src.chatbot.prompt.internal_prompt_text import translate_internal_string
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

# Tracks the in-flight streaming task for each thread_id, on this replica
# only. A plain async generator that nobody calls __anext__() on anymore
# isn't necessarily stopped -- LangGraph's Pregel loop schedules its own
# internal tasks (e.g. tool_node's asyncio.gather of parallel tool/subagent
# calls) that keep running on the shared event loop regardless of whether
# the outer stream is still being read. Only cancelling an explicit
# asyncio.Task actually raises CancelledError inside whatever it's awaiting
# right now and stops that work. Used two ways: the explicit
# /v1/chat/completions/cancel endpoint below (Streamlit's Stop button), and
# defensively at the top of chat_completions() before starting a new turn --
# two concurrent astream() calls against the same thread_id's Redis-backed
# checkpoint race on the same state and can make one turn's answer surface
# for another turn's question.
#
# Multi-replica note: this dict alone only protects turns that happen to
# land on the same replica -- production runs multiple FastAPI replicas
# behind a load balancer, so a cancel request or a new turn can easily land
# elsewhere. _publish_new_generation_token/_invalidate_generation_token/
# _watch_redis_token (below) extend this across replicas via a small
# Redis-backed "fencing token" per thread_id: whichever replica is actually
# running a turn notices -- via polling, not a direct signal -- when
# another replica has taken over or cancelled that thread_id, and cancels
# itself locally through this exact same registry.
_active_generations: dict[str, asyncio.Task] = {}

# Redis key prefix/TTL/poll-interval for the cross-replica fencing token
# described above. Not exposed via settings/YAML: these are internal
# implementation constants, not something a deploying university would
# ever need to tune.
_ACTIVE_GEN_KEY_PREFIX = f"{__name__}:active_generation:"
# Generous safety net, not a provable bound on turn duration -- recursion
# limit and per-LLM-call timeouts keep the legitimate case well under this,
# but MCP subagent timeout_seconds has no hard cap, so this exists purely
# to eventually stop an already-pathological turn rather than leak forever.
_ACTIVE_GEN_TTL_SECONDS = 60 * 30
# Sub-second, so a Stop click feels instant; still cheap on Redis even with
# many concurrent conversations across all replicas (one GET per poll per
# in-flight turn).
_ACTIVE_GEN_POLL_INTERVAL_SECONDS = 0.5


def _active_gen_key(thread_id: str) -> str:
    return f"{_ACTIVE_GEN_KEY_PREFIX}{thread_id}"


async def _publish_new_generation_token(thread_id: str) -> str | None:
    """Register this turn as the canonical one for `thread_id` across all
    replicas, by writing a fresh random token -- which implicitly
    invalidates whatever token another replica might still be watching for
    the same thread_id, without needing to know which replica that is.

    Returns None (after logging) if Redis is unreachable. This is a safety
    mechanism, not core chat functionality: callers must treat None as
    "no cross-replica protection available for this turn" and proceed
    anyway -- a Redis hiccup must never break or drop a chat turn.
    """
    token = uuid.uuid4().hex
    try:
        await redis_client.client.setex(
            _active_gen_key(thread_id), _ACTIVE_GEN_TTL_SECONDS, token
        )
        return token
    except (redis.RedisError, RuntimeError) as e:
        logger.warning(f"[ACTIVE-GEN] Could not publish generation token: {e}")
        return None


async def _invalidate_generation_token(thread_id: str) -> None:
    """Best-effort cross-replica invalidation for the explicit /cancel
    endpoint. Any replica actually running this thread_id's turn notices
    via its own watcher within one poll interval and self-cancels."""
    try:
        await redis_client.client.delete(_active_gen_key(thread_id))
    except (redis.RedisError, RuntimeError) as e:
        logger.warning(f"[ACTIVE-GEN] Could not invalidate generation token: {e}")


async def _cancel_active_generation(thread_id: str) -> bool:
    """Cancel and await any still-running generation task for `thread_id`
    on this replica. Returns True if a task was found and cancelled.

    Removes the registry entry itself rather than relying on
    _stream_cancellable's own `finally` block to do it: that block only
    runs if the *outer* wrapper generator is itself driven to exhaustion
    or explicitly closed. An abandoned client (disconnected, or Streamlit
    interrupted mid-run) just stops calling __anext__() on it -- it's
    never closed -- so without this, cancelling the inner pump task here
    stops the backend work correctly but leaves a stale (already-done)
    entry in _active_generations forever.
    """
    task = _active_generations.get(thread_id)
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if _active_generations.get(thread_id) is task:
            del _active_generations[thread_id]
        return True
    return False


async def _stream_cancellable(agen, thread_id: str, token: str | None = None):
    """
      Wrap stream_generator in a coroutine so that all the langraph running coroutines can be cancelled if required.
        _pump's Task
      └─ await agen.__anext__()               (agen = stream_generator())
           └─ await agent._graph.astream(...).__anext__()
                └─ ...LangGraph's Pregel loop...
                     └─ await asyncio.gather(tool_call_1(), tool_call_2(), ...)

    When you call task.cancel() on _pump's task, asyncio throws CancelledError in at wherever that task is currently suspended — which is somewhere down at the
    bottom of that chain.

    `token` (from _publish_new_generation_token) additionally spawns
    _watch_redis_token, a sibling task that lets a *different* replica
    cancel this same task -- see the comment above _active_generations.
    Pass None (the default) to skip cross-replica protection entirely,
    e.g. when Redis was unreachable at turn start.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    async def _pump():
        try:
            async for item in agen:
                await queue.put(item)
        except asyncio.CancelledError:
            # Expected path when _cancel_active_generation() cancels this
            # task -- the loop above has already stopped, so just let the
            # consumer below know we're done; nothing to propagate.
            pass
        except Exception as e:
            await queue.put(e)
        finally:
            await queue.put(_DONE)

    async def _watch_redis_token(pump_task: asyncio.Task):
        """Polls the shared Redis token for `thread_id`; if it no longer
        matches `token` -- overwritten by a new turn (possibly on another
        replica) or deleted by /cancel (possibly from another replica) --
        cancels `pump_task` directly (it's already in closure here, so
        there's no need to go through the thread_id-keyed
        _cancel_active_generation lookup that external callers use).

        Self-terminates as soon as `pump_task` is done for any reason,
        checked at the top of every iteration -- so it never outlives the
        task it's watching even if the outer generator this function wraps
        is merely abandoned rather than explicitly closed.

        On cancelling, also removes the _active_generations entry itself
        (identity-checked, same as _cancel_active_generation) rather than
        relying on this wrapper's own `finally` to do it -- that `finally`
        doesn't run either for an abandoned-not-closed outer generator, so
        without this the registry would leak a stale (already-done) entry
        for thread_id forever, same failure mode _cancel_active_generation
        was written to avoid.
        """
        key = _active_gen_key(thread_id)
        while not pump_task.done():
            await asyncio.sleep(_ACTIVE_GEN_POLL_INTERVAL_SECONDS)
            if pump_task.done():
                return
            try:
                current = await redis_client.client.get(key)
            except (redis.RedisError, RuntimeError) as e:
                logger.warning(
                    f"[ACTIVE-GEN] Redis unreachable while watching {thread_id}, "
                    f"falling back to same-replica-only protection for this turn: {e}"
                )
                return
            if current != token:
                reason = "missing" if current is None else "mismatched"
                logger.debug(
                    f"[ACTIVE-GEN] Token {reason} for {thread_id}; cancelling "
                    "local generation (superseded or cancelled elsewhere)"
                )
                if not pump_task.done():
                    pump_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await pump_task
                if _active_generations.get(thread_id) is pump_task:
                    del _active_generations[thread_id]
                return

    task = asyncio.create_task(_pump())
    _active_generations[thread_id] = task
    watcher = asyncio.create_task(_watch_redis_token(task)) if token else None
    try:
        # Consumer
        while True:
            item = await queue.get()
            if item is _DONE:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        if _active_generations.get(thread_id) is task:
            del _active_generations[thread_id]
        if not task.done():
            task.cancel()
        if watcher and not watcher.done():
            watcher.cancel()


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

    # Guard against two concurrent graph runs on the same thread_id (e.g.
    # the previous turn is still finishing when this one arrives) -- see
    # _active_generations above for why this matters. Cancels the local
    # task if any (same-replica fast path), then publishes a fresh Redis
    # token registering *this* turn as canonical for thread_id -- which
    # also implicitly invalidates whatever a still-running turn on a
    # *different* replica is watching, closing the same race there.
    await _cancel_active_generation(thread_id)
    generation_token = await _publish_new_generation_token(thread_id)

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

    # A cancelled turn (explicit Stop click, or the defensive preemption
    # above) can leave a dangling AIMessage(tool_calls=...) anywhere in the
    # checkpointed message list: tool_node/rewrite (graph_node_edges.py)
    # only remove the AIMessage that triggered their tool calls
    # (RemoveMessage) *after* those calls finish, in the same coroutine --
    # a cancellation while they're in flight means that removal never
    # runs. Critically, this codebase never appends ToolMessages to
    # `messages` at all (tool output goes into the separate
    # `tool_messages` state field) -- so an AIMessage with tool_calls is
    # *only* ever removed via that RemoveMessage on success. That means
    # any such message still present anywhere in the list, not just at
    # the tail, is unresolved by construction: a second cancelled turn
    # (e.g. the user's own next message also getting stopped) appends a
    # further message *after* the still-dangling one, burying it -- so
    # checking only the last message misses it (confirmed live: a real
    # session left `[..., AIMessage(tool_calls=...), HumanMessage("hi")]`
    # and a last-message-only check saw the trailing HumanMessage and
    # concluded there was nothing to strip). Left in place, agent_node
    # feeds the LLM a tool-call request with no matching response, which
    # doesn't fail fast -- it visibly confuses the model (observed: it
    # answers the *previous*, already-stopped question instead of the new
    # one). LangGraph itself does NOT resume the old tool call here -- a
    # fresh, non-None input always starts a clean run at START -- this is
    # purely about stale message *content* left behind. Checked on every
    # turn (not just right after a cancellation) so it's correct
    # regardless of which replica ends up running this turn, without
    # needing to race a cross-replica cleanup.
    if prev_state.values:
        prev_messages = prev_state.values.get("messages") or []
        dangling_ids = [
            m.id
            for m in prev_messages
            if getattr(m, "tool_calls", None) and getattr(m, "id", None)
        ]
        if dangling_ids:
            try:
                await agent._graph.aupdate_state(
                    config,
                    {"messages": [RemoveMessage(id=mid) for mid in dangling_ids]},
                )
                # Reflect the removal locally so the check below sees the
                # post-strip tail, not the stale pre-strip one.
                prev_messages = [m for m in prev_messages if m.id not in dangling_ids]
                logger.info(
                    "[ACTIVE-GEN] Stripped dangling unresolved tool call(s) left "
                    f"by (a) cancelled turn(s) for thread_id={thread_id}: {dangling_ids}"
                )
            except Exception as e:
                logger.warning(
                    f"[ACTIVE-GEN] Failed to strip dangling tool call(s) for "
                    f"thread_id={thread_id}: {e}"
                )

        # Stripping a dangling tool call above can expose a bare
        # HumanMessage with no answer at all attached to it -- or, if no
        # tool call was ever involved (cancelled during grade_documents,
        # a generate* node, or agent_node's own direct-answer path), the
        # trailing message was already a bare HumanMessage to begin with.
        # generate/generate_application/generate_teaching_degree_node
        # (graph_node_edges.py, via the shared generate_helper) always
        # append their final AIMessage through the add_messages reducer
        # on a normal completion, so a trailing HumanMessage here is only
        # possible if the previous turn never finished. Left alone,
        # agent_node sees that question still open and reasonably keeps
        # trying to answer it even when the new message is unrelated
        # (confirmed live: cancelling "can i still apply" then "hi" twice
        # left a clean-looking `[Human, Human, Human]` state that still
        # produced a fresh application-deadline search in response to
        # plain "hi"). Marking it closed here -- an internal-only message,
        # never surfaced via user_message_history -- tells the model the
        # thread is done instead of still pending.
        if prev_messages and isinstance(prev_messages[-1], HumanMessage):
            # last message should be an ai message.
            try:
                await agent._graph.aupdate_state(
                    config,
                    {
                        "messages": [
                            AIMessage(
                                content=translate_internal_string(
                                    "interrupted_response", language
                                )
                            )
                        ]
                    },
                )
                logger.info(
                    "[ACTIVE-GEN] Marked an interrupted (unanswered) previous "
                    f"turn for thread_id={thread_id}"
                )
            except Exception as e:
                logger.warning(
                    f"[ACTIVE-GEN] Failed to mark interrupted turn for "
                    f"thread_id={thread_id}: {e}"
                )

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

            except asyncio.CancelledError:
                # User-initiated stop (see _cancel_active_generation) --
                # log it the same way every other turn outcome is logged,
                # then re-raise so _stream_cancellable's pump can shut the
                # stream down cleanly. No fallback chunk/[DONE] is yielded
                # and _save_to_chat_history is deliberately not called: the
                # client already stopped watching, and saving a partial
                # answer here is exactly the stale-answer problem this is
                # fixing.
                log_event(
                    "TURN_COMPLETED",
                    "Chat turn cancelled by user",
                    query=user_message,
                    language=str(language),
                    error="cancelled",
                    latency_ms=round((time.monotonic() - turn_start) * 1000, 1),
                )
                raise

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
            _stream_cancellable(
                stream_generator(), thread_id, generation_token
            ),  # calls the stream_generator that in turn calls the graph, that calls agents that generate an answer.
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


# Same key scope as /v1/chat/completions (API_KEYS via verify_api_key), not
# HISTORY_API_KEYS -- this cancels a turn the caller itself started, it
# doesn't read or wipe conversation history, so it belongs with the
# completions scope rather than the /v1/threads/* history scope below.
@app.post("/v1/chat/completions/cancel")
async def cancel_completion(
    request: CancelRequest,
    api_key: str = Security(verify_api_key),
):
    """Cancel the in-flight streaming turn for `request.thread_id`. Cancels
    the local task if it's running on this replica (instant), and always
    invalidates the shared Redis token too (see _active_generations) so a
    turn running on a *different* replica is cancelled as well, within one
    poll interval."""
    cancelled = await _cancel_active_generation(request.thread_id)
    await _invalidate_generation_token(request.thread_id)
    return {"cancelled": cancelled}


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
