import csv
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings

MAX_AGE_DAYS = settings.log_settings.delete_logs_days

# Schedule cleanup using a cron job or similar mechanism


def cleanup_old_csv_entries(log_file: str, max_age_days: int = MAX_AGE_DAYS):
    """
    Remove entries older than specified days from CSV log file

    Args:
        log_file: Path to CSV log file
        max_age_days: Maximum age of entries in days (default: 90 = 3 months)
    """
    if not os.path.exists(log_file):
        return 0

    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    removed_count = 0

    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, newline="")

    try:
        with open(log_file, "r", newline="") as infile:
            csv_reader = csv.reader(infile)
            csv_writer = csv.writer(temp_file)

            for row in csv_reader:
                if len(row) >= 1:  # Make sure row has timestamp
                    try:
                        # Parse timestamp
                        timestamp_str = row[0]  # First column should be timestamp
                        entry_date = datetime.strptime(
                            timestamp_str, "%Y-%m-%d %H:%M:%S"
                        )

                        if entry_date >= cutoff_date:
                            csv_writer.writerow(row)
                        else:
                            removed_count += 1
                    except (ValueError, IndexError):
                        # Keep malformed rows to avoid data loss
                        csv_writer.writerow(row)
                else:
                    csv_writer.writerow(row)

        temp_file.close()

        # Replace original file with cleaned file
        shutil.move(temp_file.name, log_file)
        logger.info(f"Removed {removed_count} old entries from {log_file}")

    except Exception as e:
        temp_file.close()
        os.unlink(temp_file.name)  # Clean up temp file
        logger.error(f"Error cleaning up {log_file}: {e}")
        raise

    return removed_count


def cleanup_old_text_logs(log_file: str, max_age_days: int = MAX_AGE_DAYS):
    """
    Remove entries older than specified days from text log files
    """
    if not os.path.exists(log_file):
        return 0

    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    removed_count = 0

    temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)

    try:
        with open(log_file, "r") as infile:
            for line in infile:
                try:
                    # Extract timestamp from log line
                    # Expected format: "2025-06-16 10:30:45 - chatbot_logger - INFO - ..."
                    timestamp_str = line.split(" - ")[0]
                    entry_date = datetime.strptime(
                        timestamp_str, "%Y-%m-%d %H:%M:%S,%f"
                    )

                    if entry_date >= cutoff_date:
                        temp_file.write(line)
                    else:
                        removed_count += 1
                except (ValueError, IndexError):
                    # Keep malformed lines
                    temp_file.write(line)

        temp_file.close()
        shutil.move(temp_file.name, log_file)
        logger.info(f"Removed {removed_count} old entries from {log_file}")

    except Exception as e:
        temp_file.close()
        os.unlink(temp_file.name)
        logger.error(f"Error cleaning up {log_file}: {e}")
        raise

    return removed_count


def cleanup_all_logs(log_dir: str = "logs", max_age_days: int = MAX_AGE_DAYS):
    """Clean up all log files in the directory"""
    log_path = Path(log_dir)
    if not log_path.exists():
        return

    total_removed = 0

    # Clean CSV files
    for csv_file in log_path.glob("*.csv"):
        try:
            removed = cleanup_old_csv_entries(str(csv_file), max_age_days)
            total_removed += removed
        except Exception as e:
            logger.error(f"Failed to clean {csv_file}: {e}")

    # Clean text log files
    for log_file in log_path.glob("*.log"):
        try:
            removed = cleanup_old_text_logs(str(log_file), max_age_days)
            total_removed += removed
        except Exception as e:
            logger.error(f"Failed to clean {log_file}: {e}")

    logger.info(f"Total entries removed: {total_removed}")
    return total_removed


if __name__ == "__main__":
    cleanup_all_logs()
