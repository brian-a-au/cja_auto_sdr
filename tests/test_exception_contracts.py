"""Contract tests for CLI exception-boundary hardening."""

import json
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import cja_auto_sdr.generator as generator
from cja_auto_sdr.core.error_policies import (
    RECOVERABLE_CONNECTION_TEST_EXCEPTIONS,
    RECOVERABLE_GIT_SUBPROCESS_EXCEPTIONS,
    RECOVERABLE_LOCK_METADATA_PARSE_EXCEPTIONS,
    RECOVERABLE_OPEN_FILE_EXCEPTIONS,
    RECOVERABLE_OPTIONAL_ENRICHMENT_EXCEPTIONS,
)
from cja_auto_sdr.core.logging import RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS
from cja_auto_sdr.org.models import OrgReportConfig


def test_command_handler_exception_policy_keeps_generic_fallback() -> None:
    """CLI command handlers must retain a generic Exception fallback."""
    assert Exception in generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS


def test_optional_inventory_exception_policies_keep_generic_fallback() -> None:
    """Optional inventory paths must stay non-fatal for unexpected builder errors."""
    assert Exception in generator.RECOVERABLE_OPTIONAL_INVENTORY_EXCEPTIONS
    assert Exception in generator.RECOVERABLE_INVENTORY_SUMMARY_EXCEPTIONS


def test_git_snapshot_refetch_exception_policy_keeps_generic_fallback() -> None:
    """Optional git snapshot refetch must remain non-fatal for unexpected runtime errors."""
    assert Exception in generator.RECOVERABLE_GIT_SNAPSHOT_REFETCH_EXCEPTIONS


def test_stats_row_exception_policy_keeps_generic_fallback() -> None:
    """Stats row fallback must keep a generic per-item Exception boundary."""
    assert Exception in generator.RECOVERABLE_STATS_ROW_EXCEPTIONS


def test_connection_test_exception_policy_keeps_generic_fallback() -> None:
    """Connection test is best-effort and must stay non-fatal for unexpected errors."""
    assert Exception in RECOVERABLE_CONNECTION_TEST_EXCEPTIONS


def test_optional_enrichment_exception_policy_keeps_generic_fallback() -> None:
    """Optional snapshot enrichments must stay non-fatal for unexpected runtime errors."""
    assert Exception in RECOVERABLE_OPTIONAL_ENRICHMENT_EXCEPTIONS


def test_open_file_exception_policy_keeps_generic_fallback() -> None:
    """open_file_in_default_app must preserve its bool contract for unexpected failures."""
    assert Exception in RECOVERABLE_OPEN_FILE_EXCEPTIONS


def test_lock_metadata_parse_exception_policy_keeps_generic_fallback() -> None:
    """Advisory lock metadata parsing must never abort lock ownership flows."""
    assert Exception in RECOVERABLE_LOCK_METADATA_PARSE_EXCEPTIONS


def test_git_subprocess_exception_policy_includes_decode_failures() -> None:
    """Git wrappers must treat subprocess text decode failures as recoverable."""
    assert OSError in RECOVERABLE_GIT_SUBPROCESS_EXCEPTIONS
    assert ValueError in RECOVERABLE_GIT_SUBPROCESS_EXCEPTIONS
    assert subprocess.SubprocessError in RECOVERABLE_GIT_SUBPROCESS_EXCEPTIONS


def test_logging_boundary_exception_policy_keeps_generic_fallback() -> None:
    """Logging safety helpers must remain non-fatal for unexpected runtime errors."""
    assert Exception in RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS


@pytest.mark.parametrize("summary_mode", [True, False])
def test_optional_inventory_runner_handles_unexpected_runtime_error(summary_mode: bool) -> None:
    logger = MagicMock()

    def _raise_runtime() -> None:
        raise RuntimeError("optional builder crashed")

    result = generator._run_optional_inventory_step(
        logger=logger,
        inventory_label="derived field inventory",
        summary_mode=summary_mode,
        build_inventory=_raise_runtime,
    )

    assert result is None
    assert logger.debug.called
    if summary_mode:
        logger.warning.assert_called_once()
    else:
        logger.error.assert_called_once()
        logger.info.assert_called_once()


def test_optional_inventory_runner_uses_import_callback() -> None:
    logger = MagicMock()
    import_callback = MagicMock()

    def _raise_import_error() -> None:
        raise ImportError("missing module")

    result = generator._run_optional_inventory_step(
        logger=logger,
        inventory_label="calculated metrics inventory",
        summary_mode=False,
        build_inventory=_raise_import_error,
        on_import_error=import_callback,
    )

    assert result is None
    import_callback.assert_called_once()
    callback_arg = import_callback.call_args[0][0]
    assert isinstance(callback_arg, ImportError)
    assert "missing module" in str(callback_arg)


@pytest.mark.parametrize("output_json", [True, False])
def test_show_config_status_non_object_config_returns_controlled_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    output_json: bool,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    result = generator.show_config_status(config_file=str(config_path), output_json=output_json)

    assert result is False
    output = capsys.readouterr().out
    if output_json:
        payload = json.loads(output)
        assert payload["valid"] is False
        assert "must contain a JSON object" in payload["error"]
    else:
        assert "must contain a JSON object" in output


def test_stats_row_fallback_returns_error_row_for_unexpected_runtime_error() -> None:
    mock_cja = MagicMock()
    mock_cja.getDataView.side_effect = RuntimeError("stats failure")

    row = generator._collect_stats_row_with_fallback(mock_cja, "dv_bad", logging.getLogger(__name__))

    assert row["id"] == "dv_bad"
    assert row["name"] == "ERROR"
    assert "stats failure" in row["description"]


def test_show_stats_continues_after_unexpected_runtime_error(capsys: pytest.CaptureFixture) -> None:
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
    ):
        mock_client = MagicMock()

        def _get_dataview(dv_id: str) -> dict[str, str]:
            if dv_id == "dv_bad":
                raise RuntimeError("per-view runtime failure")
            return {"name": f"Name {dv_id}", "owner": {"name": "owner"}, "description": "desc"}

        mock_client.getDataView.side_effect = _get_dataview
        mock_client.getMetrics.return_value = [{"id": "m1"}]
        mock_client.getDimensions.return_value = [{"id": "d1"}]
        mock_cjapy.CJA.return_value = mock_client

        result = generator.show_stats(["dv_bad", "dv_ok"], output_format="json")

    assert result is False
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 2
    error_row = next(item for item in payload["stats"] if item["id"] == "dv_bad")
    ok_row = next(item for item in payload["stats"] if item["id"] == "dv_ok")
    assert error_row["name"] == "ERROR"
    assert ok_row["name"] == "Name dv_ok"


def test_validate_data_view_recoverable_api_error_returns_false() -> None:
    mock_cja = MagicMock()
    mock_cja.getDataView.side_effect = ValueError("unexpected validation failure")

    result = generator.validate_data_view(mock_cja, "dv_contract", logging.getLogger(__name__))

    assert result is False


def test_run_org_report_unexpected_runtime_error_returns_controlled_failure(tmp_path: Path) -> None:
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
    ):
        mock_cjapy.CJA.side_effect = RuntimeError("bootstrap exploded")

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=True,
        )

    assert ok is False
    assert exceeded is False
