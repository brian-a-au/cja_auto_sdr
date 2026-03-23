"""Consistency and contract tests for discovery component fetching/counting."""

import io
import json
import logging
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import pytest

import cja_auto_sdr.generator as generator
from cja_auto_sdr.generator import (
    describe_dataview,
    list_dimensions,
    list_metrics,
    run_dry_run,
    show_stats,
)


@pytest.mark.parametrize(
    ("fetch_spec", "method_name", "expected_args", "expected_kwargs"),
    [
        (
            generator._METRICS_COMPONENT_FETCH_SPEC,
            "getMetrics",
            ("dv_test",),
            {"inclType": "hidden", "full": True},
        ),
        (
            generator._DIMENSIONS_COMPONENT_FETCH_SPEC,
            "getDimensions",
            ("dv_test",),
            {"inclType": "hidden", "full": True},
        ),
        (
            generator._SEGMENTS_COMPONENT_FETCH_SPEC,
            "getFilters",
            (),
            {"dataIds": "dv_test", "full": True},
        ),
        (
            generator._CALCULATED_METRICS_COMPONENT_FETCH_SPEC,
            "getCalculatedMetrics",
            (),
            {"dataIds": "dv_test", "full": True},
        ),
    ],
)
def test_fetch_component_payload_honors_component_fetch_specs(
    fetch_spec,
    method_name,
    expected_args,
    expected_kwargs,
):
    """All component families should follow their declarative fetch-spec contract."""
    cja = MagicMock()
    expected_payload = [{"id": "row_1"}]
    getattr(cja, method_name).return_value = expected_payload

    payload = generator._fetch_component_payload(cja, "dv_test", fetch_spec)

    assert payload == expected_payload
    getattr(cja, method_name).assert_called_once_with(*expected_args, **expected_kwargs)


@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.generator.configure_cjapy")
@patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
def test_hidden_component_counts_are_consistent_across_describe_list_and_stats(
    _mock_profile,
    mock_configure,
    mock_cjapy,
):
    """describe/list/stats should all count hidden metrics/dimensions consistently."""
    mock_configure.return_value = (True, "config", None)
    cja = mock_cjapy.CJA.return_value
    cja.getDataView.return_value = {
        "id": "dv_1",
        "name": "Parity View",
        "owner": {"name": "Alice"},
        "description": "Parity check",
        "parentDataGroupId": "conn_1",
        "created": "2025-01-01",
        "modified": "2025-01-02",
    }

    def _get_metrics(_dv_id: str, **kwargs):
        assert kwargs == {"inclType": "hidden", "full": True}
        return [{"id": "m_visible"}, {"id": "m_hidden"}]

    def _get_dimensions(_dv_id: str, **kwargs):
        assert kwargs == {"inclType": "hidden", "full": True}
        return [{"id": "d_visible"}, {"id": "d_hidden"}]

    cja.getMetrics.side_effect = _get_metrics
    cja.getDimensions.side_effect = _get_dimensions
    cja.getFilters.return_value = []
    cja.getCalculatedMetrics.return_value = []

    describe_out = io.StringIO()
    with redirect_stdout(describe_out):
        assert describe_dataview("dv_1", output_format="json") is True
    describe_payload = json.loads(describe_out.getvalue())

    metrics_out = io.StringIO()
    with redirect_stdout(metrics_out):
        assert list_metrics("dv_1", output_format="json") is True
    metrics_payload = json.loads(metrics_out.getvalue())

    dimensions_out = io.StringIO()
    with redirect_stdout(dimensions_out):
        assert list_dimensions("dv_1", output_format="json") is True
    dimensions_payload = json.loads(dimensions_out.getvalue())

    stats_out = io.StringIO()
    with redirect_stdout(stats_out):
        assert show_stats(["dv_1"], output_format="json", output_file="-", quiet=True) is True
    stats_payload = json.loads(stats_out.getvalue())

    assert describe_payload["dataView"]["components"]["metrics"] == 2
    assert describe_payload["dataView"]["components"]["dimensions"] == 2
    assert metrics_payload["count"] == 2
    assert dimensions_payload["count"] == 2
    assert stats_payload["stats"][0]["metrics"] == 2
    assert stats_payload["stats"][0]["dimensions"] == 2
    assert stats_payload["stats"][0]["total_components"] == 4


@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.generator.configure_cjapy")
def test_show_stats_error_shaped_component_payload_falls_back_to_error_row(
    mock_configure,
    mock_cjapy,
):
    """Error-shaped component payloads should not be treated as numeric counts."""
    mock_configure.return_value = (True, "config", None)
    cja = mock_cjapy.CJA.return_value
    cja.getDataView.return_value = {"name": "Parity View", "owner": {"name": "Alice"}, "description": ""}
    cja.getMetrics.return_value = {"statusCode": 500, "message": "timeout"}
    cja.getDimensions.return_value = [{"id": "d_visible"}]

    stats_out = io.StringIO()
    with redirect_stdout(stats_out):
        assert show_stats(["dv_1"], output_format="json", output_file="-", quiet=True) is True
    payload = json.loads(stats_out.getvalue())

    assert payload["count"] == 1
    assert payload["stats"][0]["name"] == "ERROR"
    assert payload["stats"][0]["metrics"] == 0
    assert payload["stats"][0]["dimensions"] == 0
    assert payload["totals"]["components"] == 0


@patch("cja_auto_sdr.generator.validate_config_file", return_value=True)
@patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {}))
@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.cli.commands.discovery.make_api_call_with_retry")
def test_run_dry_run_uses_hidden_inclusive_component_fetch_contract(
    mock_retry,
    mock_cjapy,
    _mock_configure,
    _mock_validate_config,
    capsys: pytest.CaptureFixture,
):
    """dry-run should fetch metrics/dimensions with hidden-inclusive args via shared contract."""
    mock_cja = MagicMock()
    mock_cjapy.CJA.return_value = mock_cja
    mock_cja.getDataViews.return_value = []
    mock_cja.getDataView.return_value = {"id": "dv_1", "name": "DryRun View"}
    mock_cja.getMetrics.return_value = [{"id": "m_visible"}, {"id": "m_hidden"}]
    mock_cja.getDimensions.return_value = [{"id": "d_visible"}, {"id": "d_hidden"}]

    observed_operations: list[str] = []

    def _retry_passthrough(api_call, *args, **kwargs):
        observed_operations.append(kwargs.get("operation_name", ""))
        return api_call(*args)

    mock_retry.side_effect = _retry_passthrough

    logger = logging.getLogger("test_discovery_component_consistency_dry_run")
    result = run_dry_run(["dv_1"], "config.json", logger)

    assert result is True
    assert "getMetrics(dv_1)" in observed_operations
    assert "getDimensions(dv_1)" in observed_operations
    mock_cja.getMetrics.assert_called_once_with("dv_1", inclType="hidden", full=True)
    mock_cja.getDimensions.assert_called_once_with("dv_1", inclType="hidden", full=True)
    assert "Components: 2 metrics, 2 dimensions" in capsys.readouterr().out
