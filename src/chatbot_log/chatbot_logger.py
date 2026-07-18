import atexit
import contextvars
import json
import logging
import os
import socket
import sys
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue

# ---------------------------------------------------------------------------
# Log level
# ---------------------------------------------------------------------------
# Driven by an environment variable so it can differ between dev and prod
# without code changes. Defaults to INFO, which is safe for production
# (DEBUG-level breadcrumbs are opt-in via LOG_LEVEL=DEBUG, e.g. locally).
_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").strip().upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)

# ---------------------------------------------------------------------------
# Replica / instance identifier
# ---------------------------------------------------------------------------
# Docker sets HOSTNAME to the container id by default; this lets log lines
# from different replicas be told apart once they're aggregated centrally
# (e.g. by `docker logs`, a log driver, or a future Promtail/Loki pipeline).
_INSTANCE_ID = os.getenv("HOSTNAME") or socket.gethostname()

# ---------------------------------------------------------------------------
# Per-request context: thread_id / request_id
# ---------------------------------------------------------------------------
# Bound once per request (see bind_request_context) and automatically
# attached to every subsequent log line by _ContextFilter — no need to pass
# thread_id into every logger.debug/info call by hand. Scoped naturally:
# FastAPI runs each request in its own asyncio Task and Streamlit runs each
# session on its own thread, so concurrent requests never see each other's
# bound values, and nothing needs to be reset at the end of a request.
_thread_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "askuos_thread_id", default="-"
)
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "askuos_request_id", default="-"
)


def bind_request_context(thread_id: str = None, request_id: str = None) -> None:
    """Bind thread_id/request_id for the current asyncio task (or thread) so
    every subsequent log line in this request carries them automatically.
    Call once, near the top of a request handler, as soon as the ids are
    known.
    """
    if thread_id is not None:
        _thread_id_var.set(str(thread_id))
    if request_id is not None:
        _request_id_var.set(str(request_id))


class _ContextFilter(logging.Filter):
    """Attaches the currently-bound thread_id/request_id/instance_id to
    every record. Runs on the calling thread/task (before the record is
    handed to the queue), so it correctly reads whatever was bound for the
    request currently being handled.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.thread_id = _thread_id_var.get()
        record.request_id = _request_id_var.get()
        record.instance_id = _INSTANCE_ID
        return True


# Attribute names present on a bare LogRecord. Anything else found on a
# record — custom fields passed via `extra=...`, e.g. tag/node/latency_ms/
# decision/reason, plus thread_id/request_id/instance_id from the filter
# above — is treated as a structured field and included in the JSON output.
_STANDARD_RECORD_ATTRS = set(
    vars(logging.LogRecord("x", 0, "x", 0, "x", None, None)).keys()
) | {"message", "asctime"}


class _JsonFormatter(logging.Formatter):
    """Renders each log line as a single JSON object so it can be filtered
    and aggregated on real fields (thread_id, tag, latency_ms, ...) — e.g. by
    Loki's `| json` parser — instead of regexing free text.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_"):
                payload.setdefault(key, value)

        return json.dumps(payload, default=str, ensure_ascii=False)


def log_event(tag: str, message: str, level: int = logging.INFO, **fields) -> None:
    """Emit a structured log line: a machine-readable `tag` plus arbitrary
    structured fields (e.g. node="judge_node", decision="no", reason=...,
    latency_ms=123), on top of the auto-attached thread_id/request_id/
    instance_id.

    Prefer this over an f-string for anything meant to be queried or
    aggregated later (decisions, latencies, counts) rather than just read by
    a human — e.g.:

        log_event("JUDGE_NODE", "Evaluated agent decision",
                   decision=score.judgement_binary, reason=score.reason)

    Existing plain logger.debug/info/... calls keep working unchanged; they
    just won't have separate queryable fields beyond thread_id/request_id/
    instance_id until migrated to log_event.
    """
    # stacklevel=2 so the JSON record's module/line reflect the real call
    # site (e.g. graph_node_edges.py) rather than this wrapper function.
    logger.log(level, message, extra={"tag": tag, **fields}, stacklevel=2)


logger = logging.getLogger("chatbot_logger")
logger.setLevel(_LOG_LEVEL)
# Don't bubble records up to the root logger — this is the only logger this
# app configures, and double-propagation would risk duplicate output if some
# dependency (e.g. Streamlit) attaches its own root handlers.
logger.propagate = False
logger.addFilter(_ContextFilter())

# ---------------------------------------------------------------------------
# Non-blocking logging via background threads.
# ---------------------------------------------------------------------------
# logging.Handler.emit() does synchronous I/O. Called directly, every
# logger.info/debug/error(...) call blocks the calling thread — including
# the FastAPI event loop thread and Streamlit's per-session threads — for the
# duration of the write. QueueHandler/QueueListener decouples "record the
# event" (a fast, thread-safe queue.put) from "write the bytes" (done on a
# background thread by the listener), for both async and sync callers alike
# — no asyncio-specific code needed, since Streamlit's threads and FastAPI's
# coroutines are just different callers of the same thread-safe logger.
#
# Two independent sinks, each with its OWN queue and listener thread, so
# slowness in one can never delay the other:

# ---------------------------------------------------------------------------
# Sink 1: stdout — replica-safe by construction (Docker captures and
# isolates each container's stdout natively). Used for live tailing via
# `docker compose logs` / `docker logs`.
# ---------------------------------------------------------------------------
_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.setFormatter(_JsonFormatter())

_stdout_queue: "Queue" = Queue(-1)  # unbounded: never blocks/drops on enqueue
logger.addHandler(QueueHandler(_stdout_queue))

_stdout_listener = QueueListener(
    _stdout_queue, _stdout_handler, respect_handler_level=True
)
_stdout_listener.start()
atexit.register(_stdout_listener.stop)

# ---------------------------------------------------------------------------
# Sink 2: a per-replica file inside the `logs` volume — this is what lets
# log history survive `docker compose down` + `up` (named volumes aren't
# removed unless `-v`/`--volumes` is passed), while staying replica-safe:
# each replica writes to its OWN file, named after its instance id, so
# there's no cross-process write/rotation contention like there would be
# with one shared file across replicas (which is exactly what we moved away
# from previously). Same JSON formatter as stdout, so it's already in the
# right shape for Promtail/Loki to ingest later without changes.
#
# This whole sink is best-effort and optional: if the volume isn't mounted,
# permissions are wrong, or the disk is full, we log a warning (via the
# stdout sink, already up by this point) and continue without file logging
# rather than letting a durability nice-to-have take the whole app down.
# Everything that can fail here (creating the directory, opening the file)
# happens BEFORE the queue/handler are wired up, so a failure never leaves
# an orphaned queue with nothing consuming it.
# ---------------------------------------------------------------------------
_LOG_DIR = os.getenv("LOG_DIR", "logs")
_LOG_FILE = os.path.join(_LOG_DIR, f"log-{_INSTANCE_ID}.log")

try:
    # exist_ok=True avoids a race if multiple replicas start at the same
    # time and all try to create the shared directory concurrently.
    os.makedirs(_LOG_DIR, exist_ok=True)
    _file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=1024 * 1024 * 250, backupCount=7
    )
    _file_handler.setFormatter(_JsonFormatter())

    _file_queue: "Queue" = Queue(-1)
    logger.addHandler(QueueHandler(_file_queue))

    # A separate listener/thread from stdout's — a slow disk or volume
    # backend can never delay stdout output (or vice versa); each sink is
    # fully isolated.
    _file_listener = QueueListener(
        _file_queue, _file_handler, respect_handler_level=True
    )
    _file_listener.start()
    atexit.register(_file_listener.stop)
except OSError as e:
    logger.warning(
        f"[SYSTEM] Could not set up file-based logging at {_LOG_FILE!r} "
        f"({e}); continuing with stdout-only logging.",
        extra={"tag": "LOGGING_FILE_SINK_UNAVAILABLE"},
    )
