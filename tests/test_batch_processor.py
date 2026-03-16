"""Tests for BatchProcessor class"""

import logging
import os
import sys
from concurrent.futures.process import BrokenProcessPool
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.core.exceptions import OutputError
from cja_auto_sdr.generator import BatchProcessor, ProcessingResult, WorkerArgs


@pytest.fixture
def mock_logger():
    """Create a mock logger"""
    logger = Mock(spec=logging.Logger)
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    return logger


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory"""
    output_dir = tmp_path / "batch_output"
    output_dir.mkdir()
    return str(output_dir)


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary config file"""
    import json

    config_data = {
        "org_id": "test_org@AdobeOrg",
        "client_id": "test_client_id",
        "secret": "test_secret",
        "scopes": "openid, AdobeID",
    }
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)


@pytest.fixture
def successful_result():
    """Create a successful processing result"""
    return ProcessingResult(
        data_view_id="dv_test_12345",
        data_view_name="Test Data View",
        success=True,
        duration=5.0,
        metrics_count=100,
        dimensions_count=50,
        dq_issues_count=5,
        output_file="/path/to/output.xlsx",
        file_size_bytes=1024,
    )


@pytest.fixture
def failed_result():
    """Create a failed processing result"""
    return ProcessingResult(
        data_view_id="dv_test_failed",
        data_view_name="Failed Data View",
        success=False,
        duration=2.0,
        error_message="Connection timeout",
    )


class TestBatchProcessorInit:
    """Tests for BatchProcessor initialization"""

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_with_defaults(self, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test initialization with default parameters"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)

        assert processor.config_file == mock_config_file
        assert processor.output_dir == temp_output_dir
        assert processor.workers == 4
        assert processor.continue_on_error is False
        assert processor.log_level == "INFO"
        assert processor.output_format == "excel"
        assert processor.enable_cache is False

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_with_custom_workers(self, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test initialization with custom worker count"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, workers=8)

        assert processor.workers == 8

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_with_continue_on_error(self, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test initialization with continue_on_error enabled"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, continue_on_error=True)

        assert processor.continue_on_error is True

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_with_cache_settings(self, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test initialization with cache settings"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            enable_cache=True,
            cache_size=500,
            cache_ttl=1800,
        )

        assert processor.enable_cache is True
        assert processor.cache_size == 500
        assert processor.cache_ttl == 1800

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_creates_output_directory(self, mock_setup_logging, mock_config_file, tmp_path):
        """Test that initialization creates output directory if needed"""
        mock_setup_logging.return_value = Mock()

        new_output_dir = tmp_path / "new_batch_output"
        assert not new_output_dir.exists()

        BatchProcessor(config_file=mock_config_file, output_dir=str(new_output_dir))

        assert new_output_dir.exists()

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_generates_batch_id(self, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test that initialization generates a batch ID"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)

        assert processor.batch_id is not None
        assert len(processor.batch_id) == 8

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_with_all_output_formats(self, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test initialization with 'all' output format"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, output_format="all")

        assert processor.output_format == "all"


class TestBatchProcessorProcessBatch:
    """Tests for process_batch method"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_single_success(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        successful_result,
    ):
        """Test processing a single data view successfully"""
        mock_setup_logging.return_value = Mock()

        # Setup mock progress bar
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        # Setup mock executor
        mock_future = Mock()
        mock_future.result.return_value = successful_result
        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        # Patch as_completed to return our futures
        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)
            results = processor.process_batch(["dv_test_12345"])

        assert len(results["successful"]) == 1
        assert len(results["failed"]) == 0
        assert results["total"] == 1

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_single_failure(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        failed_result,
    ):
        """Test processing a single data view that fails"""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.return_value = failed_result
        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, continue_on_error=True)
            results = processor.process_batch(["dv_test_failed"])

        assert len(results["successful"]) == 0
        assert len(results["failed"]) == 1

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_mixed_results(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        successful_result,
        failed_result,
    ):
        """Test processing multiple data views with mixed results"""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future1 = Mock()
        mock_future1.result.return_value = successful_result
        mock_future2 = Mock()
        mock_future2.result.return_value = failed_result

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.side_effect = [mock_future1, mock_future2]
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future1, mock_future2]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, continue_on_error=True)
            results = processor.process_batch(["dv_test_12345", "dv_test_failed"])

        assert len(results["successful"]) == 1
        assert len(results["failed"]) == 1
        assert results["total"] == 2

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_exception_handling(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Test handling of exceptions during batch processing"""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.side_effect = ValueError("Unexpected error")

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, continue_on_error=True)
            results = processor.process_batch(["dv_test_12345"])

        assert len(results["failed"]) == 1
        assert "Unexpected error" in results["failed"][0].error_message

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_broken_process_pool_handling(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """BrokenProcessPool should be captured as failed result, not raised."""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.side_effect = BrokenProcessPool("worker terminated abruptly")

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, continue_on_error=True)
            results = processor.process_batch(["dv_test_12345"])

        assert len(results["failed"]) == 1
        assert "worker terminated abruptly" in results["failed"][0].error_message

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_exception_cancels_remaining_when_continue_on_error_false(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Exceptions should cancel outstanding futures when stopping early."""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.side_effect = ValueError("Boom")
        mock_future.cancel = Mock()

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                continue_on_error=False,
            )
            processor.process_batch(["dv_test_12345"])

        mock_future.cancel.assert_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_broken_process_pool_cancels_when_continue_on_error_false(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """BrokenProcessPool should trigger cancellation when stop-on-error is enabled."""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.side_effect = BrokenProcessPool("worker terminated abruptly")
        mock_future.cancel = Mock()

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                continue_on_error=False,
            )
            processor.process_batch(["dv_test_12345"])

        mock_future.cancel.assert_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_unexpected_exception_captured_as_failed(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Plain Exception from worker/executor plumbing should be captured, not raised."""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.side_effect = RuntimeError("executor plumbing failure")

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir, continue_on_error=True)
            results = processor.process_batch(["dv_test_12345"])

        assert len(results["failed"]) == 1
        assert "executor plumbing failure" in results["failed"][0].error_message

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_unexpected_exception_cancels_when_stop_on_error(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Plain Exception should cancel remaining futures when continue_on_error=False."""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.side_effect = RuntimeError("executor plumbing failure")
        mock_future.cancel = Mock()

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                continue_on_error=False,
            )
            processor.process_batch(["dv_test_12345"])

        mock_future.cancel.assert_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_shared_cache_shutdown_on_interrupt(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Shared cache should be shutdown even when processing is interrupted."""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.side_effect = KeyboardInterrupt()
        mock_future.cancel = Mock()

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with (
            patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]),
            patch("cja_auto_sdr.pipeline.batch.emit_diagnostic") as mock_emit_diagnostic,
        ):
            processor = BatchProcessor(
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                continue_on_error=True,
                enable_cache=True,
                shared_cache=True,
            )
            mock_shared_cache = Mock()
            mock_shared_cache.get_statistics.return_value = {"hits": 0, "misses": 0, "hit_rate": 0.0}
            processor._shared_cache = mock_shared_cache

            with pytest.raises(KeyboardInterrupt):
                processor.process_batch(["dv_test_12345"])

            mock_shared_cache.shutdown.assert_called_once()
            mock_emit_diagnostic.assert_called_once()

        args, kwargs = mock_emit_diagnostic.call_args
        assert args[1] == "shared_cache_summary"
        assert args[2] == "resource"
        assert kwargs["hits"] == 0
        assert kwargs["misses"] == 0
        assert kwargs["hit_rate"] == 0.0
        assert kwargs["size"] == 0
        assert kwargs["evictions"] == 0

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_process_batch_calculates_total_duration(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        successful_result,
    ):
        """Test that total duration is calculated"""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.return_value = successful_result
        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)
            results = processor.process_batch(["dv_test_12345"])

        assert "total_duration" in results
        assert results["total_duration"] >= 0


class TestBatchProcessorPrintSummary:
    """Tests for print_summary method"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("builtins.print")
    def test_print_summary_all_successful(
        self,
        mock_print,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        successful_result,
    ):
        """Test summary output with all successful results"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)

        results = {"successful": [successful_result], "failed": [], "total": 1, "total_duration": 5.0}

        processor.print_summary(results)

        # Verify print was called with summary information
        print_calls = [str(c) for c in mock_print.call_args_list]
        assert any("SUMMARY" in c for c in print_calls)

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("builtins.print")
    def test_print_summary_with_failures(
        self,
        mock_print,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        successful_result,
        failed_result,
    ):
        """Test summary output with some failures"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)

        results = {"successful": [successful_result], "failed": [failed_result], "total": 2, "total_duration": 7.0}

        processor.print_summary(results)

        print_calls = [str(c) for c in mock_print.call_args_list]
        assert any("Failed" in c for c in print_calls)

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("builtins.print")
    def test_print_summary_calculates_success_rate(
        self,
        mock_print,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        successful_result,
        failed_result,
    ):
        """Test that success rate is calculated correctly"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)

        results = {"successful": [successful_result], "failed": [failed_result], "total": 2, "total_duration": 7.0}

        processor.print_summary(results)

        # Should print 50% success rate
        print_calls = [str(c) for c in mock_print.call_args_list]
        assert any("50" in c for c in print_calls)

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("builtins.print")
    def test_print_summary_empty_results(self, mock_print, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test summary output with no results"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)

        results = {"successful": [], "failed": [], "total": 0, "total_duration": 0.0}

        processor.print_summary(results)

        # Should still print summary without errors
        mock_print.assert_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("builtins.print")
    def test_print_summary_calculates_total_file_size(
        self,
        mock_print,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Test that total file size is calculated"""
        mock_setup_logging.return_value = Mock()

        processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)

        result1 = ProcessingResult(
            data_view_id="dv_1",
            data_view_name="DV1",
            success=True,
            duration=1.0,
            file_size_bytes=1024,
        )
        result2 = ProcessingResult(
            data_view_id="dv_2",
            data_view_name="DV2",
            success=True,
            duration=1.0,
            file_size_bytes=2048,
        )

        results = {"successful": [result1, result2], "failed": [], "total": 2, "total_duration": 2.0}

        processor.print_summary(results)

        # Total should be 3072 bytes
        mock_print.assert_called()


class TestBatchProcessorWorkerArgs:
    """Tests for worker argument preparation"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_worker_args_include_all_settings(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        successful_result,
    ):
        """Test that worker args include all processor settings"""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_future = Mock()
        mock_future.result.return_value = successful_result

        submitted_args = []

        def capture_submit(func, args):
            submitted_args.append(args)
            return mock_future

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.side_effect = capture_submit
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[mock_future]):
            processor = BatchProcessor(
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                enable_cache=True,
                cache_size=500,
                skip_validation=True,
            )
            processor.process_batch(["dv_test_12345"])

        # Verify args were passed as WorkerArgs
        assert len(submitted_args) == 1
        args = submitted_args[0]
        assert isinstance(args, WorkerArgs)
        assert args.data_view_id == "dv_test_12345"
        assert args.config_file == mock_config_file
        assert args.production_mode is False
        assert args.batch_id is not None


class TestBatchProcessorEdgeCases:
    """Tests for edge cases"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_empty_data_view_list(
        self,
        mock_tqdm,
        mock_executor,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Test processing with empty data view list"""
        mock_setup_logging.return_value = Mock()

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor.return_value = mock_executor_instance

        with patch("cja_auto_sdr.generator.as_completed", return_value=[]):
            processor = BatchProcessor(config_file=mock_config_file, output_dir=temp_output_dir)
            results = processor.process_batch([])

        assert results["total"] == 0
        assert len(results["successful"]) == 0
        assert len(results["failed"]) == 0

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_init_permission_error(self, mock_setup_logging, mock_config_file):
        """Test handling of permission error during output dir creation"""
        mock_setup_logging.return_value = Mock()

        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Access denied")):
            with pytest.raises(OutputError, match="Permission denied"):
                BatchProcessor(config_file=mock_config_file, output_dir="/nonexistent/restricted/path")
