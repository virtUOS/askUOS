import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Create a logger
logger = logging.getLogger("chatbot_logger")
logger.setLevel(logging.DEBUG)  # Set the logging level

# Define the logs directory and files
log_dir = "logs"
log_file = os.path.join(log_dir, "log.log")  # Changed to .log extension

# Create the logs directory if it doesn't exist
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Create a rotating file handler for general logs (INFO and above)
max_bytes = 1024 * 1024 * 250  # 250 MB
backup_count = 7


file_handler = RotatingFileHandler(
    log_file, maxBytes=max_bytes, backupCount=backup_count
)
file_handler.setLevel(logging.INFO)  # INFO level and above (excludes DEBUG)
file_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s [File: %(pathname)s, Line: %(lineno)d]"
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Create a console handler for debugging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s [File: %(pathname)s, Line: %(lineno)d]"
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)
