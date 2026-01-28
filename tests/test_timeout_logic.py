import unittest
import logging
from unittest.mock import MagicMock, patch
from pathlib import Path
import time
from core.batch_processor import BatchProcessor

# Configure logging to see output
logging.basicConfig(level=logging.INFO)


class TestGranularTimeout(unittest.TestCase):
    @patch("config.settings")
    def test_file_timeout(self, mock_settings):
        # 1. Setup mocks
        # Set a very short timeout for the test
        mock_settings.FILE_TIMEOUT_SECONDS = 0.5
        mock_settings.BATCH_TIMEOUT_SECONDS = 300

        # Mock the processor to simulate a slow operation
        mock_processor = MagicMock()

        def slow_process(path):
            print(f"Starting slow process for {path}...")
            time.sleep(1.0)  # Sleep longer than the timeout
            print("Finished slow process (should not happen if timeout works)")
            return "Processed"

        mock_processor.process.side_effect = slow_process

        # Initialize batch processor with mocked dependencies
        batch_processor = BatchProcessor(processor=mock_processor)

        # 2. Execute
        # We need a dummy file path
        dummy_path = Path("test_timeout.pdf")

        print(f"\nTesting timeout with limit={mock_settings.FILE_TIMEOUT_SECONDS}s...")
        start_time = time.time()

        # Call the private method directly for isolated testing
        result = batch_processor._process_single_file(dummy_path)

        elapsed = time.time() - start_time
        print(f"Operation took {elapsed:.2f}s")

        # 3. Verify
        # Result should be None (timeout occurred)
        self.assertIsNone(result)

        # Time should be roughly equal to timeout (plus small overhead), but definitely less than the sleep time
        self.assertGreaterEqual(
            elapsed, 0.45
        )  # Should wait at least the timeout duration

    @patch("config.settings")
    def test_file_success(self, mock_settings):
        # 1. Setup mocks
        # Set a long timeout
        mock_settings.FILE_TIMEOUT_SECONDS = 1.0

        # Mock the processor to simulate a fast operation
        mock_processor = MagicMock()
        mock_processor.process.return_value = "Success"

        batch_processor = BatchProcessor(processor=mock_processor)
        dummy_path = Path("test_success.pdf")

        # 2. Execute
        print("\nTesting success within limit...")
        result = batch_processor._process_single_file(dummy_path)

        # 3. Verify
        self.assertEqual(result, "Success")


if __name__ == "__main__":
    unittest.main()
