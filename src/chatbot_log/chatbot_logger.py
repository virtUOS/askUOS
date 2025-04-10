import logging
import os
import sys
from logging.handlers import RotatingFileHandler


class CsvFormatter(logging.Formatter):
    def format(self, record):
        created = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return f"{created},{record.pathname},{record.lineno},{record.name},{record.levelname},{record.getMessage()}"


class CsvFilter(logging.Filter):
    def filter(self, record):
        # Save only INFO and above levels:
        return record.levelno >= logging.INFO


# Create a logger
logger = logging.getLogger("chatbot_logger")
logger.setLevel(logging.DEBUG)  # Set the logging level

# Define the logs directory and files
log_dir = "logs"
log_file = os.path.join(log_dir, "log.csv")
error_log_file = os.path.join(log_dir, "error.log")

# Create the logs directory if it doesn't exist
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Create a rotating CSV file handler for general logs
max_bytes = 1024 * 1024 * 250  # 250 MB
backup_count = 7

csv_handler = RotatingFileHandler(
    log_file, maxBytes=max_bytes, backupCount=backup_count
)
csv_handler.setLevel(logging.DEBUG)
csv_formatter = CsvFormatter()
csv_handler.setFormatter(csv_formatter)
csv_handler.addFilter(CsvFilter())
logger.addHandler(csv_handler)

# Create a rotating file handler for error logs
error_handler = RotatingFileHandler(
    error_log_file, maxBytes=max_bytes, backupCount=backup_count
)
error_handler.setLevel(logging.WARNING)
error_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s [File: %(pathname)s, Line: %(lineno)d]"
)
error_handler.setFormatter(error_formatter)
logger.addHandler(error_handler)

# Create a console handler for debugging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s [File: %(pathname)s, Line: %(lineno)d]"
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)
