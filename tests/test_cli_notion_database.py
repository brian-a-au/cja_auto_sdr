"""CLI flag wiring + dispatch validation for the v3.8.0 database flags."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.cli.parser import parse_arguments
from cja_auto_sdr.generator import RunMode, _validate_semantic_flag_relationships


def test_notion_database_id_flag_parses() -> None:
    args = parse_arguments(["dv1", "--format", "notion", "--notion-database-id", "abc-123"])
    assert args.notion_database_id == "abc-123"


def test_notion_create_database_flag_parses() -> None:
    args = parse_arguments(["dv1", "--format", "notion", "--notion-create-database"])
    assert args.notion_create_database is True


def test_notion_database_id_default_is_none() -> None:
    args = parse_arguments(["dv1", "--format", "notion"])
    assert args.notion_database_id is None
    assert args.notion_create_database is False


def test_org_report_accepts_notion_format() -> None:
    args = parse_arguments(["--org-report", "--format", "notion"])
    assert args.org_report is True
    assert args.format == "notion"


# ---------------------------------------------------------------------------
# WorkerArgs carries both new fields
# ---------------------------------------------------------------------------


def test_worker_args_has_notion_database_id() -> None:
    from cja_auto_sdr.pipeline.models import WorkerArgs

    wa = WorkerArgs(data_view_id="dv_test", notion_database_id="db-abc")
    assert wa.notion_database_id == "db-abc"


def test_worker_args_has_notion_create_database() -> None:
    from cja_auto_sdr.pipeline.models import WorkerArgs

    wa = WorkerArgs(data_view_id="dv_test", notion_create_database=True)
    assert wa.notion_create_database is True


def test_worker_args_defaults() -> None:
    from cja_auto_sdr.pipeline.models import WorkerArgs

    wa = WorkerArgs(data_view_id="dv_test")
    assert wa.notion_database_id is None
    assert wa.notion_create_database is False


# ---------------------------------------------------------------------------
# ProcessingConfig carries both new fields
# ---------------------------------------------------------------------------


def test_processing_config_has_notion_database_id() -> None:
    from cja_auto_sdr.pipeline.models import ProcessingConfig

    cfg = ProcessingConfig(notion_database_id="db-xyz")
    assert cfg.notion_database_id == "db-xyz"


def test_processing_config_has_notion_create_database() -> None:
    from cja_auto_sdr.pipeline.models import ProcessingConfig

    cfg = ProcessingConfig(notion_create_database=True)
    assert cfg.notion_create_database is True


def test_processing_config_defaults() -> None:
    from cja_auto_sdr.pipeline.models import ProcessingConfig

    cfg = ProcessingConfig()
    assert cfg.notion_database_id is None
    assert cfg.notion_create_database is False


# ---------------------------------------------------------------------------
# BatchConfig carries both new fields
# ---------------------------------------------------------------------------


def test_batch_config_has_notion_database_id() -> None:
    from cja_auto_sdr.pipeline.models import BatchConfig

    cfg = BatchConfig(notion_database_id="db-batch")
    assert cfg.notion_database_id == "db-batch"


def test_batch_config_has_notion_create_database() -> None:
    from cja_auto_sdr.pipeline.models import BatchConfig

    cfg = BatchConfig(notion_create_database=True)
    assert cfg.notion_create_database is True


def test_batch_config_defaults() -> None:
    from cja_auto_sdr.pipeline.models import BatchConfig

    cfg = BatchConfig()
    assert cfg.notion_database_id is None
    assert cfg.notion_create_database is False


# ---------------------------------------------------------------------------
# process_single_dataview accepts both new params and forwards to write_notion_output
# ---------------------------------------------------------------------------


def test_process_single_dataview_accepts_notion_database_id() -> None:
    """process_single_dataview signature accepts notion_database_id without TypeError."""
    import inspect

    from cja_auto_sdr import generator

    sig = inspect.signature(generator.process_single_dataview)
    assert "notion_database_id" in sig.parameters


def test_process_single_dataview_accepts_notion_create_database() -> None:
    """process_single_dataview signature accepts notion_create_database without TypeError."""
    import inspect

    from cja_auto_sdr import generator

    sig = inspect.signature(generator.process_single_dataview)
    assert "notion_create_database" in sig.parameters


def test_write_notion_output_called_with_database_id(tmp_path) -> None:
    """write_notion_output receives database_id from process_single_dataview."""
    from unittest.mock import Mock

    import pandas as pd

    from cja_auto_sdr.generator import process_single_dataview

    sample_metrics = pd.DataFrame(
        [{"id": "m1", "name": "Metric 1", "type": "standard", "description": "", "title": "Metric 1"}]
    )
    sample_dimensions = pd.DataFrame(
        [{"id": "d1", "name": "Dimension 1", "type": "string", "description": "", "title": "Dimension 1"}]
    )
    sample_dv_info = {"id": "dv_test_12345", "name": "Test DV", "owner": {"name": "Owner"}, "description": ""}

    mock_logger = Mock()
    mock_logger.handlers = []

    mock_fetcher = Mock()
    mock_fetcher.fetch_all_data.return_value = (sample_metrics, sample_dimensions, sample_dv_info)

    mock_dq_checker = Mock()
    mock_dq_checker.issues = []
    mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
        columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"]
    )

    with (
        patch("cja_auto_sdr.generator.setup_logging", return_value=mock_logger),
        patch("cja_auto_sdr.generator.initialize_cja", return_value=Mock()),
        patch("cja_auto_sdr.generator.ParallelAPIFetcher", return_value=mock_fetcher),
        patch("cja_auto_sdr.generator.DataQualityChecker", return_value=mock_dq_checker),
        patch("cja_auto_sdr.output.writers.notion.write_notion_output") as mock_wno,
    ):
        mock_wno.return_value = str(tmp_path / "out.notion")

        process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=str(tmp_path / "config.json"),
            output_dir=str(tmp_path),
            output_format="notion",
            notion_database_id="db-test-123",
        )

    mock_wno.assert_called_once()
    _, kwargs = mock_wno.call_args
    assert kwargs.get("database_id") == "db-test-123"


# ---------------------------------------------------------------------------
# _run_single_mode forwards notion_database_id + notion_create_database to
# process_single_dataview
# ---------------------------------------------------------------------------


def _make_fake_single_result() -> MagicMock:
    result = MagicMock()
    result.success = True
    result.data_view_name = "Test DV"
    result.emitted_output_files = ["/tmp/out.xlsx"]
    result.output_file = "/tmp/out.xlsx"
    result.file_size_formatted = "1.0 KB"
    result.metrics_count = 5
    result.dimensions_count = 10
    result.dq_issues_count = 0
    result.segments_count = 0
    result.segments_high_complexity = 0
    result.calculated_metrics_count = 0
    result.calculated_metrics_high_complexity = 0
    result.derived_fields_count = 0
    result.derived_fields_high_complexity = 0
    result.total_high_complexity = 0
    return result


def _make_fake_single_args(**overrides) -> MagicMock:  # type: ignore[return]
    args = MagicMock()
    args.quiet = True
    args.config_file = "config.json"
    args.output_dir = "."
    args.log_format = "text"
    args.enable_cache = False
    args.cache_size = 1000
    args.cache_ttl = 3600
    args.skip_validation = False
    args.max_issues = 0
    args.clear_cache = False
    args.show_timings = False
    args.notion_force_new = False
    args.notion_database_id = None
    args.notion_create_database = False
    # Override getattr(..., False) behaviour for inventory flags
    args.include_segments_inventory = False
    args.include_calculated_metrics = False
    args.include_derived_inventory = False
    args.inventory_only = False
    args.metrics_only = False
    args.dimensions_only = False
    args.allow_partial = False
    args.production = False
    args.profile = None
    args.git_commit = False
    args.open = False
    for key, val in overrides.items():
        setattr(args, key, val)
    return args


def test_run_single_mode_forwards_notion_database_id() -> None:
    """_run_single_mode passes notion_database_id from args to process_single_dataview."""
    from cja_auto_sdr.cli import execution

    captured_kwargs: dict = {}

    def fake_process_single_dataview(dv_id, **kwargs):
        captured_kwargs.update(kwargs)
        return _make_fake_single_result()

    args = _make_fake_single_args(notion_database_id="db-single-123")
    generator_mod = execution._generator_module()

    with patch.object(generator_mod, "process_single_dataview", side_effect=fake_process_single_dataview):
        execution._run_single_mode(
            args,
            data_views=["dv_abc"],
            effective_log_level="ERROR",
            sdr_format="notion",
            processing_start_time=0.0,
            quality_report_only=False,
            inventory_order=[],
            api_tuning_config=None,
            circuit_breaker_config=None,
        )

    assert captured_kwargs.get("notion_database_id") == "db-single-123"


def test_run_single_mode_forwards_notion_create_database() -> None:
    """_run_single_mode passes notion_create_database from args to process_single_dataview."""
    from cja_auto_sdr.cli import execution

    captured_kwargs: dict = {}

    def fake_process_single_dataview(dv_id, **kwargs):
        captured_kwargs.update(kwargs)
        return _make_fake_single_result()

    args = _make_fake_single_args(notion_create_database=True)
    generator_mod = execution._generator_module()

    with patch.object(generator_mod, "process_single_dataview", side_effect=fake_process_single_dataview):
        execution._run_single_mode(
            args,
            data_views=["dv_abc"],
            effective_log_level="ERROR",
            sdr_format="notion",
            processing_start_time=0.0,
            quality_report_only=False,
            inventory_order=[],
            api_tuning_config=None,
            circuit_breaker_config=None,
        )

    assert captured_kwargs.get("notion_create_database") is True


# ---------------------------------------------------------------------------
# _run_batch_mode forwards both new params to BatchProcessor.__init__
# ---------------------------------------------------------------------------


def test_run_batch_mode_forwards_notion_database_id() -> None:
    """_run_batch_mode passes notion_database_id to BatchProcessor."""
    from cja_auto_sdr.cli import execution

    captured_init_kwargs: dict = {}

    class FakeBatchProcessor:
        def __init__(self, **kwargs):
            captured_init_kwargs.update(kwargs)

        def process_batch(self, data_views):
            return {"successful": [], "failed": [], "total": 0, "total_duration": 0.0}

    args = MagicMock()
    args.quiet = True
    args.config_file = "config.json"
    args.output_dir = "."
    args.log_format = "text"
    args.enable_cache = False
    args.cache_size = 1000
    args.cache_ttl = 3600
    args.skip_validation = False
    args.max_issues = 0
    args.clear_cache = False
    args.show_timings = False
    args.workers = 2
    args.continue_on_error = False
    args.notion_force_new = False
    args.notion_database_id = "db-batch-456"
    args.notion_create_database = False

    generator_mod = execution._generator_module()

    with patch.object(generator_mod, "BatchProcessor", FakeBatchProcessor):
        execution._run_batch_mode(
            args,
            data_views=["dv_1", "dv_2"],
            effective_log_level="ERROR",
            sdr_format="notion",
            processing_start_time=0.0,
            workers_auto=False,
            quality_report_only=False,
            inventory_order=[],
            api_tuning_config=None,
            circuit_breaker_config=None,
        )

    assert captured_init_kwargs.get("notion_database_id") == "db-batch-456"


def test_run_batch_mode_forwards_notion_create_database() -> None:
    """_run_batch_mode passes notion_create_database to BatchProcessor."""
    from cja_auto_sdr.cli import execution

    captured_init_kwargs: dict = {}

    class FakeBatchProcessor:
        def __init__(self, **kwargs):
            captured_init_kwargs.update(kwargs)

        def process_batch(self, data_views):
            return {"successful": [], "failed": [], "total": 0, "total_duration": 0.0}

    args = MagicMock()
    args.quiet = True
    args.config_file = "config.json"
    args.output_dir = "."
    args.log_format = "text"
    args.enable_cache = False
    args.cache_size = 1000
    args.cache_ttl = 3600
    args.skip_validation = False
    args.max_issues = 0
    args.clear_cache = False
    args.show_timings = False
    args.workers = 2
    args.continue_on_error = False
    args.notion_force_new = False
    args.notion_database_id = None
    args.notion_create_database = True

    generator_mod = execution._generator_module()

    with patch.object(generator_mod, "BatchProcessor", FakeBatchProcessor):
        execution._run_batch_mode(
            args,
            data_views=["dv_1", "dv_2"],
            effective_log_level="ERROR",
            sdr_format="notion",
            processing_start_time=0.0,
            workers_auto=False,
            quality_report_only=False,
            inventory_order=[],
            api_tuning_config=None,
            circuit_breaker_config=None,
        )

    assert captured_init_kwargs.get("notion_create_database") is True


# ---------------------------------------------------------------------------
# workers.py — ProcessingConfig built from WorkerArgs carries new fields
# ---------------------------------------------------------------------------


def test_worker_builds_processing_config_with_notion_database_id() -> None:
    """WorkerArgs.notion_database_id is forwarded into the ProcessingConfig built by workers.py."""
    from cja_auto_sdr.pipeline.models import WorkerArgs
    from cja_auto_sdr.pipeline.workers import process_single_dataview_worker

    wa = WorkerArgs(data_view_id="dv_test", notion_database_id="db-worker-789")
    captured: dict = {}

    def fake_process_single_dataview(dv_id, processing_config=None, **kwargs):
        if processing_config is not None:
            captured["notion_database_id"] = processing_config.notion_database_id
        result = MagicMock()
        result.success = True
        result.data_view_name = "Test"
        result.emitted_output_files = []
        result.output_file = ""
        result.file_size_bytes = 0
        return result

    import cja_auto_sdr.pipeline.workers as workers_mod

    generator_mod = workers_mod._generator_module()
    with patch.object(generator_mod, "process_single_dataview", side_effect=fake_process_single_dataview):
        process_single_dataview_worker(wa)

    assert captured.get("notion_database_id") == "db-worker-789"


def test_worker_builds_processing_config_with_notion_create_database() -> None:
    """WorkerArgs.notion_create_database is forwarded into the ProcessingConfig built by workers.py."""
    from cja_auto_sdr.pipeline.models import WorkerArgs
    from cja_auto_sdr.pipeline.workers import process_single_dataview_worker

    wa = WorkerArgs(data_view_id="dv_test", notion_create_database=True)
    captured: dict = {}

    def fake_process_single_dataview(dv_id, processing_config=None, **kwargs):
        if processing_config is not None:
            captured["notion_create_database"] = processing_config.notion_create_database
        result = MagicMock()
        result.success = True
        result.data_view_name = "Test"
        result.emitted_output_files = []
        result.output_file = ""
        result.file_size_bytes = 0
        return result

    import cja_auto_sdr.pipeline.workers as workers_mod

    generator_mod = workers_mod._generator_module()
    with patch.object(generator_mod, "process_single_dataview", side_effect=fake_process_single_dataview):
        process_single_dataview_worker(wa)

    assert captured.get("notion_create_database") is True


# ---------------------------------------------------------------------------
# Env fallback: NOTION_DATABASE_ID env var resolves at execution call sites
# ---------------------------------------------------------------------------


def test_env_fallback_notion_database_id_in_single_mode() -> None:
    """When args.notion_database_id is None, NOTION_DATABASE_ID env var is used."""
    import os

    from cja_auto_sdr.cli import execution

    captured_kwargs: dict = {}

    def fake_process_single_dataview(dv_id, **kwargs):
        captured_kwargs.update(kwargs)
        return _make_fake_single_result()

    args = _make_fake_single_args()  # notion_database_id=None by default
    generator_mod = execution._generator_module()

    env_patch = {"NOTION_DATABASE_ID": "db-from-env"}
    with (
        patch.dict(os.environ, env_patch),
        patch.object(generator_mod, "process_single_dataview", side_effect=fake_process_single_dataview),
    ):
        execution._run_single_mode(
            args,
            data_views=["dv_abc"],
            effective_log_level="ERROR",
            sdr_format="notion",
            processing_start_time=0.0,
            quality_report_only=False,
            inventory_order=[],
            api_tuning_config=None,
            circuit_breaker_config=None,
        )

    assert captured_kwargs.get("notion_database_id") == "db-from-env"


# ---------------------------------------------------------------------------
# Task 6: --org-report allowed; --workers > 1 and --watch rejected with notion
# ---------------------------------------------------------------------------


def test_org_report_notion_allowed() -> None:
    """--format notion must be ALLOWED in org-report mode (Task 6)."""
    args = argparse.Namespace(
        format="notion",
        skip_validation=False,
        push_to_notion=None,
        workers=1,
        watch_data_views=None,
    )
    # Must NOT raise — org-report is now a permitted mode for --format notion.
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.ORG_REPORT)


def test_workers_gt_1_with_notion_rejected(capsys) -> None:
    """--workers > 1 with --format notion must exit 1."""
    args = argparse.Namespace(
        format="notion",
        skip_validation=False,
        push_to_notion=None,
        workers=4,
        watch_data_views=None,
    )
    with pytest.raises(SystemExit) as exc_info:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.SDR)
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "--workers > 1 is not supported with --format notion" in captured.err


def test_watch_with_notion_rejected(capsys) -> None:
    """--watch combined with --format notion must exit 1."""
    args = argparse.Namespace(
        format="notion",
        skip_validation=False,
        push_to_notion=None,
        workers=1,
        watch_data_views=["dv_abc123"],
        watch_interval="1h",
        watch_threshold=1,
        output=None,
        org_report=False,
        diff=False,
        quality_policy=None,
        fail_on_quality=None,
        batch=False,
        list_dataviews=False,
        list_connections=False,
        list_datasets=False,
        snapshot=None,
        list_snapshots=False,
        prune_snapshots=False,
        diff_snapshot=None,
        compare_with_prev=False,
        compare_snapshots=None,
        diff_labels=None,
        inventory_summary=False,
        include_all_inventory=False,
        git_init=False,
        git_commit=False,
        profile_list=False,
        profile_import=None,
        profile_add=None,
        profile_test=None,
        profile_show=None,
        git_push=False,
        stats=False,
        describe_dataview=None,
        list_metrics=None,
        list_dimensions=None,
        list_segments=None,
        list_calculated_metrics=None,
        trending_window=None,
        data_views=None,
    )
    with pytest.raises(SystemExit) as exc_info:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.SDR)
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "--watch is not supported with --format notion" in captured.err
