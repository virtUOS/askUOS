import csv
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append("/app/src")

from src.chatbot_log.log_cleanup import (
    cleanup_all_logs,
    cleanup_old_csv_entries,
    cleanup_old_text_logs,
)


class TestLogCleanup(unittest.TestCase):
    def setUp(self):
        """Set up test environment with temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.test_dir)

    def create_test_csv_file(
        self, filename: str, old_entries: int = 5, new_entries: int = 3
    ):
        """Create a test CSV file with old and new entries"""
        filepath = self.test_path / filename

        # Generate test data
        old_date = datetime.now() - timedelta(days=100)  # Older than 90 days
        new_date = datetime.now() - timedelta(days=30)  # Newer than 90 days

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)

            # Add old entries
            for i in range(old_entries):
                timestamp = (old_date + timedelta(hours=i)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                writer.writerow(
                    [timestamp, f"old_user_{i}", f"old_message_{i}", "old_response"]
                )

            # Add new entries
            for i in range(new_entries):
                timestamp = (new_date + timedelta(hours=i)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                writer.writerow(
                    [timestamp, f"new_user_{i}", f"new_message_{i}", "new_response"]
                )

        return filepath, old_entries, new_entries

    def create_test_log_file(
        self, filename: str, old_entries: int = 4, new_entries: int = 2
    ):
        """Create a test log file with old and new entries"""
        filepath = self.test_path / filename

        old_date = datetime.now() - timedelta(days=100)
        new_date = datetime.now() - timedelta(days=30)

        with open(filepath, "w") as f:
            # Add old entries
            for i in range(old_entries):
                timestamp = (old_date + timedelta(hours=i)).strftime(
                    "%Y-%m-%d %H:%M:%S,%f"
                )
                f.write(f"{timestamp} - chatbot_logger - INFO - Old log entry {i}\n")

            # Add new entries
            for i in range(new_entries):
                timestamp = (new_date + timedelta(hours=i)).strftime(
                    "%Y-%m-%d %H:%M:%S,%f"
                )
                f.write(f"{timestamp} - chatbot_logger - INFO - New log entry {i}\n")

        return filepath, old_entries, new_entries

    def count_lines_in_file(self, filepath):
        """Count lines in a file"""
        with open(filepath, "r") as f:
            return sum(1 for line in f)

    def test_cleanup_single_csv_file(self):
        """Test cleanup of a single CSV file"""
        filepath, old_count, new_count = self.create_test_csv_file("test.csv")

        # Verify initial state
        initial_lines = self.count_lines_in_file(filepath)
        self.assertEqual(initial_lines, old_count + new_count)

        # Run cleanup
        removed = cleanup_old_csv_entries(str(filepath))

        # Verify results
        remaining_lines = self.count_lines_in_file(filepath)
        self.assertEqual(removed, old_count)
        self.assertEqual(remaining_lines, new_count)

    def test_cleanup_multiple_csv_files(self):
        """Test cleanup of multiple CSV files"""
        # Create multiple CSV files
        file1, old1, new1 = self.create_test_csv_file("logs1.csv", 3, 2)
        file2, old2, new2 = self.create_test_csv_file("logs2.csv", 4, 1)
        file3, old3, new3 = self.create_test_csv_file("data.csv", 2, 3)

        total_old = old1 + old2 + old3
        total_new = new1 + new2 + new3

        # Run cleanup on all files
        total_removed = cleanup_all_logs(str(self.test_path))

        # Verify results
        self.assertEqual(total_removed, total_old)
        self.assertEqual(self.count_lines_in_file(file1), new1)
        self.assertEqual(self.count_lines_in_file(file2), new2)
        self.assertEqual(self.count_lines_in_file(file3), new3)

    def test_cleanup_single_log_file(self):
        """Test cleanup of a single log file"""
        filepath, old_count, new_count = self.create_test_log_file("test.log")

        initial_lines = self.count_lines_in_file(filepath)
        self.assertEqual(initial_lines, old_count + new_count)

        removed = cleanup_old_text_logs(str(filepath))

        remaining_lines = self.count_lines_in_file(filepath)
        self.assertEqual(removed, old_count)
        self.assertEqual(remaining_lines, new_count)

    def test_cleanup_multiple_log_files(self):
        """Test cleanup of multiple log files"""
        file1, old1, new1 = self.create_test_log_file("app1.log", 3, 2)
        file2, old2, new2 = self.create_test_log_file("app2.log", 5, 1)

        total_old = old1 + old2

        total_removed = cleanup_all_logs(str(self.test_path))

        self.assertEqual(total_removed, total_old)
        self.assertEqual(self.count_lines_in_file(file1), new1)
        self.assertEqual(self.count_lines_in_file(file2), new2)

    def test_cleanup_mixed_files(self):
        """Test cleanup of both CSV and log files together"""
        # Create mixed file types
        csv_file, csv_old, csv_new = self.create_test_csv_file("data.csv", 3, 2)
        log_file, log_old, log_new = self.create_test_log_file("app.log", 4, 1)

        total_old = csv_old + log_old

        total_removed = cleanup_all_logs(str(self.test_path))

        self.assertEqual(total_removed, total_old)
        self.assertEqual(self.count_lines_in_file(csv_file), csv_new)
        self.assertEqual(self.count_lines_in_file(log_file), log_new)

    def test_cleanup_nonexistent_directory(self):
        """Test cleanup on non-existent directory"""
        result = cleanup_all_logs("/nonexistent/path")
        self.assertIsNone(result)

    def test_cleanup_empty_directory(self):
        """Test cleanup on empty directory"""
        result = cleanup_all_logs(str(self.test_path))
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
