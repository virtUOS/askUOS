import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.append("/app")

from src.chatbot_log.chatbot_logger import log_event, logger
from src.config.core_config import settings

MAX_AGE_DAYS = settings.log_settings.delete_logs_days

# Schedule cleanup using a cron job, a scheduled task, or similar.
#
# Each replica writes its own file (logs/log-{instance_id}.log, one JSON
# object per line — see chatbot_logger.py's _JsonFormatter — plus
# RotatingFileHandler backups log-{instance_id}.log.1, .2, ...). A file can
# span far more than `max_age_days` of history (rotation is size-triggered,
# not time-triggered), so cleanup prunes individual stale entries out of each
# file rather than deleting the whole file based on its mtime.

_ROTATED_BACKUP_RE = re.compile(r"\.log\.\d+$")


def _entry_timestamp(line: str) -> float | None:
    """Return the Unix timestamp of a JSON log line, or None if it can't be
    parsed (malformed line, or missing/unparseable `timestamp` field).
    """
    try:
        payload = json.loads(line)
        return datetime.fromisoformat(payload["timestamp"]).timestamp()
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def cleanup_stale_log_files(
    log_dir: str = None, max_age_days: int = MAX_AGE_DAYS
) -> int:
    """Delete log entries older than `max_age_days` out of each per-replica
    log file (and its rotated backups), keeping the rest.

    Args:
        log_dir: Directory containing the per-replica log files. Defaults to
            the same directory chatbot_logger.py writes to (the `LOG_DIR` env
            var, or "logs").
        max_age_days: Log entries older than this many days are removed.

    Returns:
        Number of log entries removed across all files.
    """
    log_dir = log_dir or os.getenv("LOG_DIR", "logs")
    log_path = Path(log_dir)
    if not log_path.exists():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    entries_removed = 0
    files_deleted = 0

    # Matches both the active file (log-<instance>.log) and rotated
    # backups (log-<instance>.log.1, log-<instance>.log.2, ...).
    for file in log_path.glob("log-*.log*"):
        try:
            with file.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            kept = []
            for line in lines:
                ts = _entry_timestamp(line)
                # Keep lines whose timestamp can't be parsed rather than
                # silently discarding data we can't confirm is actually
                # stale.
                if ts is None or ts >= cutoff:
                    kept.append(line)
                else:
                    entries_removed += 1

            if len(kept) == len(lines):
                continue

            if kept:
                # Rewrite via the SAME open file object (r+, no rename) so
                # the file keeps its inode. chatbot_logger.py's
                # RotatingFileHandler opens each file in append mode
                # (O_APPEND), which always writes at the current end of
                # file as tracked by the kernel — so a still-running
                # replica writing to this same active file keeps appending
                # correctly after this truncate+rewrite. Renaming/replacing
                # the file instead would leave that replica's open handle
                # pointing at an orphaned, now-nameless inode.
                with file.open("r+", encoding="utf-8") as f:
                    f.seek(0)
                    f.writelines(kept)
                    f.truncate()
            elif _ROTATED_BACKUP_RE.search(file.name):
                # Only rotated backups are safe to remove entirely: nothing
                # still holds them open for writing (rotation is done once a
                # backup is created), unlike the active log-<instance>.log
                # file.
                file.unlink()
                files_deleted += 1
            else:
                with file.open("w", encoding="utf-8"):
                    pass
        except OSError as e:
            logger.error(f"[SYSTEM] Failed to clean up log file {file}: {e}")

    log_event(
        "LOG_CLEANUP",
        "Removed stale log entries",
        log_dir=str(log_dir),
        max_age_days=max_age_days,
        entries_removed=entries_removed,
        files_deleted=files_deleted,
    )
    return entries_removed


# Backward-compatible entry point name (used by the `if __name__ ==
# "__main__"` block below and any external scheduler already pointing at
# `cleanup_all_logs`) — now just delegates to the entry-level sweep.
def cleanup_all_logs(log_dir: str = None, max_age_days: int = MAX_AGE_DAYS) -> int:
    return cleanup_stale_log_files(log_dir=log_dir, max_age_days=max_age_days)


if __name__ == "__main__":
    cleanup_all_logs()
