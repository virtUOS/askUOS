import os
import sys
import time
from pathlib import Path

sys.path.append("/app")

from src.chatbot_log.chatbot_logger import log_event, logger
from src.config.core_config import settings

MAX_AGE_DAYS = settings.log_settings.delete_logs_days

# Schedule cleanup using a cron job, a scheduled task, or similar.
#
# NOTE: This module used to prune individual rows/lines out of a single,
# continuously-appended log file (one shared log.log / log.csv). That no
# longer matches how logging works: each replica now writes its own file
# (logs/log-{instance_id}.log, plus RotatingFileHandler backups
# log-{instance_id}.log.1, .2, ...), and a fresh file is started on every
# container restart rather than one file being appended to forever.


def cleanup_stale_log_files(
    log_dir: str = None, max_age_days: int = MAX_AGE_DAYS
) -> int:
    """Delete whole log files (and their rotated backups) not modified in
    `max_age_days`.

    Args:
        log_dir: Directory containing the per-replica log files. Defaults to
            the same directory chatbot_logger.py writes to (the `LOG_DIR` env
            var, or "logs").
        max_age_days: Files not modified within this many days are deleted.

    Returns:
        Number of files deleted.
    """
    log_dir = log_dir or os.getenv("LOG_DIR", "logs")
    log_path = Path(log_dir)
    if not log_path.exists():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    removed = 0
    freed_bytes = 0

    # Matches both the active file (log-<instance>.log) and rotated
    # backups (log-<instance>.log.1, log-<instance>.log.2, ...).
    for file in log_path.glob("log-*.log*"):
        try:
            stat = file.stat()
            if stat.st_mtime < cutoff:
                size = stat.st_size
                file.unlink()
                removed += 1
                freed_bytes += size
        except OSError as e:
            logger.error(f"[SYSTEM] Failed to clean up log file {file}: {e}")

    log_event(
        "LOG_CLEANUP",
        "Removed stale log files",
        log_dir=str(log_dir),
        max_age_days=max_age_days,
        files_removed=removed,
        bytes_freed=freed_bytes,
    )
    return removed


# Backward-compatible entry point name (used by the `if __name__ ==
# "__main__"` block below and any external scheduler already pointing at
# `cleanup_all_logs`) — now just delegates to the mtime-based sweep.
def cleanup_all_logs(log_dir: str = None, max_age_days: int = MAX_AGE_DAYS) -> int:
    return cleanup_stale_log_files(log_dir=log_dir, max_age_days=max_age_days)


if __name__ == "__main__":
    cleanup_all_logs()
