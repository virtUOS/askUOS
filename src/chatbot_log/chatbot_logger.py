import logging
import csv
import sys

class CsvFormatter(logging.Formatter):
    def format(self, record):
        created = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return f"{created},{record.name},{record.levelname},{record.getMessage()}"


# Create a logger
logger = logging.getLogger('chatbot_logger')
logger.setLevel(logging.DEBUG)  # Set the logging level


# Create a CSV file handler and set the formatter
csv_handler = logging.FileHandler('log.csv')
csv_handler.setLevel(logging.DEBUG)
csv_formatter = CsvFormatter()
csv_handler.setFormatter(csv_formatter)
logger.addHandler(csv_handler)

