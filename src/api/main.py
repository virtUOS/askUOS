import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, HTTPException, Security, WebSocket, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.api.helpers import (
    _completion_id,
    _extract_text_content,
    _format_references,
    _make_chunk,
    _make_completion,
)
from src.api.models import ChatCompletionRequest, ChatRequest, Message
from src.chatbot.agents.graph import CampusManagementOpenAIToolsAgent
from src.chatbot.prompt.main import get_system_prompt
from src.chatbot.prompt.prompt_date import get_current_date
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: Move intizialization of singletons and settings here
    # Startup: eagerly initialize the singleton so the first request isn't slow
    agent = CampusManagementOpenAIToolsAgent()
    await agent._ensure_async_initialized()
    yield
    # Shutdown: clean up Redis connection
    await agent.cleanup()


# Load valid keys
_valid_api_keys: Set[str] = set(json.loads(os.getenv("API_KEYS", "[]")))

_security = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> str:
    """Validate the Bearer token against known API keys."""
    if credentials.credentials not in _valid_api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return credentials.credentials


app = FastAPI(lifespan=lifespan, title="AksUOS API")

GENERATE_NODES = frozenset(
    {
        "generate",
        "generate_application",
        "generate_teaching_degree_node",
    }
)


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: str = Security(verify_api_key),
):
    """
    curl -X POST http://localhost:8000/v1/chat/completions \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer sk-askUOS-abc123" \
        -d '{
        "model": "askUOS-agent",
        "messages": [{"role": "user", "content": "Can I study math? (answer shortly)"}],
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

    agent = CampusManagementOpenAIToolsAgent()

    # Fresh thread_id if non provided (this means that the client sends all chat history e.g., Librechat)
    thread_id = request.thread_id if request.thread_id else str(uuid.uuid4())

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
        "language": "Deutsch",
        "visited_links": [],
        "doc_references": [],
        "about_application": False,
        "teaching_degree": False,
        "rewrite_query": False,
    }

    completion_id = _completion_id()
    created = int(time.time())
    model = request.model

    # Snapshot previous references
    prev_state = await agent._graph.aget_state(config)
    if prev_state.values:
        prev_links_count = len(prev_state.values.get("visited_links", []))
        prev_refs_count = len(prev_state.values.get("doc_references", []))
    else:
        prev_links_count = 0
        prev_refs_count = 0

    # ─── Streaming ─────────────────────────────────────

    if request.stream:

        async def stream_generator():
            streamed = False

            # Role chunk (first chunk announces the role)
            yield _make_chunk(completion_id, created, model, role="assistant")

            async for msg, metadata in agent._graph.astream(
                input_data,
                config=config,
                stream_mode="messages",
            ):
                if (
                    msg.content
                    and not isinstance(msg, HumanMessage)
                    and not isinstance(msg, ToolMessage)
                    and (
                        metadata["langgraph_node"] == "generate"
                        or metadata["langgraph_node"] == "generate_application"
                        or metadata["langgraph_node"] == "generate_teaching_degree_node"
                    )
                ):
                    text = _extract_text_content(msg.content)
                    if text:
                        streamed = True
                        yield _make_chunk(completion_id, created, model, content=text)

            # Direct response (no tools used)
            if not streamed:
                state = await agent._graph.aget_state(config)
                content = _extract_text_content(state.values["messages"][-1].content)
                yield _make_chunk(completion_id, created, model, content=content)

            # Stream references
            final_state = await agent._graph.aget_state(config)
            values = final_state.values
            new_links = list(set(values.get("visited_links", [])[prev_links_count:]))
            new_refs = values.get("doc_references", [])[prev_refs_count:]
            refs_text = _format_references(new_links, new_refs)
            if refs_text:
                yield _make_chunk(completion_id, created, model, content=refs_text)

            # Final chunk with finish_reason
            yield _make_chunk(completion_id, created, model, finish_reason="stop")
            yield "data: [DONE]\n\n"

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

    result = await agent._graph.ainvoke(input_data, config=config)
    content = _extract_text_content(result["messages"][-1].content)

    new_links = list(set(result.get("visited_links", [])[prev_links_count:]))
    new_refs = result.get("doc_references", [])[prev_refs_count:]
    refs_text = _format_references(new_links, new_refs)

    return JSONResponse(
        _make_completion(completion_id, created, model, content, refs_text)
    )


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    api_key: str = Security(verify_api_key),
):
    """
    Stream endpoint — just raw text
    Example:
    curl -X POST http://localhost:8000/chat/stream \
            -H "Content-Type: application/json"  \
            -H "Authorization: Bearer sk-askUOS-abc123" \
            -d '{"message": "Welche Fristen gelten für ein Auslandssemester?", "thread_id": "test-123", "language": "English"}' \
            --no-buffer
    """
    agent = CampusManagementOpenAIToolsAgent()

    async def text_generator():
        config = {
            "configurable": {"thread_id": request.thread_id},
            "recursion_limit": settings.application.recursion_limit,
        }

        input_data = {
            "messages": [HumanMessage(content=request.message)],
            "user_initial_query": request.message,
            "current_date": get_current_date(settings.language.lower()),
            "visited_links": [],
            "doc_references": [],
            "about_application": False,
            "teaching_degree": False,
            "rewrite_query": False,
            "language": request.language,
        }

        # Snapshot previous references so we only return NEW ones
        prev_state = await agent._graph.aget_state(config)
        if prev_state.values:
            prev_links_count = len(prev_state.values.get("visited_links", []))
            prev_refs_count = len(prev_state.values.get("doc_references", []))
        else:
            prev_links_count = 0
            prev_refs_count = 0

        streamed = False

        async for msg, metadata in agent._graph.astream(
            input_data,
            config,
            stream_mode="messages",
        ):
            if (
                msg.content
                and not isinstance(msg, HumanMessage)
                and not isinstance(msg, ToolMessage)
                and (
                    metadata["langgraph_node"] == "generate"
                    or metadata["langgraph_node"] == "generate_application"
                    or metadata["langgraph_node"] == "generate_teaching_degree_node"
                )
            ):

                text = msg.text

                if text:
                    streamed = True
                    yield text
        # ── Graph finished ──

        # Direct response — agent answered without tools
        if not streamed:
            state = await agent._graph.aget_state(config)
            content = _extract_text_content(state.values["messages"][-1].content)
            yield content

        # Append references at the end of the stream
        final_state = await agent._graph.aget_state(config)
        values = final_state.values
        new_links = list(set(values.get("visited_links", [])[prev_links_count:]))
        new_refs = values.get("doc_references", [])[prev_refs_count:]

        if new_links or new_refs:
            yield "\n\n---\n\n"
            if new_links:
                yield "**References:**\n"
                for link in new_links:
                    yield f"- {link}\n"
            if new_refs:
                yield "**Documents:**\n"
                for ref in new_refs:
                    if isinstance(ref, dict):
                        yield f"- {ref.get('source', '')}, p. {ref.get('page', '')}\n"
                    else:
                        yield f"- {ref}\n"

    return StreamingResponse(text_generator(), media_type="text/plain")


@app.get("/chat/references/{thread_id}")
async def get_references(thread_id: str):
    """
    Get references (URLs visited or docs retrieved from vector db) after streaming is done
    """
    agent = CampusManagementOpenAIToolsAgent()
    config = {"configurable": {"thread_id": thread_id}}
    state = await agent._graph.aget_state(config)
    return {
        "links": state.values.get("visited_links", []),
        "doc_references": state.values.get("doc_references", []),
    }


# connected_clients: List[WebSocket] = []

# @app.websocket("/ws/chat/{session_id}")
# async def websocket_endpoint(websocket: WebSocket, session_id: str):
#     graph = CampusManagementOpenAIToolsAgent.run()
#     thread_id = uuid.uuid4()
#     current_date = get_current_date(settings.language.lower())
#     conversation_summary = ""
#     history = []
#     user_input = ("Wo liegt der NC bei Sport?",)
#     system_user_prompt = get_system_prompt(
#         conversation_summary, history, user_input, current_date
#     )
#     await websocket.accept()
#     try:
#         while True:
#             data = await websocket.receive_json()
#             question = data.get("question")

#             config = {
#                 "configurable": {"thread_id": thread_id},
#                 "recursion_limit": settings.application.recursion_limit,  # This amounts to two laps of the graph # https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
#             }

#             async for event in graph._graph.astream(
#                 {"messages": [("user", question)]}, config=config
#             ):
#                 await websocket.send_json({"type": "token", "content": event})

#             await websocket.send_json({"type": "complete"})
#     except Exception as e:
#         await websocket.send_json({"type": "error", "content": str(e)})


# @app.post("/api/v1/summary")
# async def conversation_summary():
#     pass


# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
