from __future__ import annotations

import logging
import runpy
import sys
import types
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.__main__ import (
    _COMPLETION_OPTION,
    _fast_path_allowed_option_dests,
    _fast_path_options_fit_policy,
    _OptionScanResult,
    _OptionSpec,
    _primary_fast_path_option_dest,
    _resolve_non_version_fast_path_request,
    _scan_option_tokens,
)
from cja_auto_sdr.core.discovery_payloads import (
    _assess_expected_lookup_id,
    _coerce_lookup_scalar_text,
    _has_minimum_dataview_lookup_metadata,
    _is_legacy_unknown_lookup_placeholder,
    _is_truthy_marker,
    _lookup_value_has_substance,
    _normalize_dataview_lookup_payload,
    _unknown_lookup_placeholder_reason,
    _unknown_placeholder_diagnostic_key,
)
from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.models import (
    ComponentDistribution,
    DataViewCluster,
    DataViewSummary,
    OrgReportComparisonInput,
    OrgReportConfig,
    TrendingSnapshot,
    _has_complete_data_view_ids,
    _has_complete_high_similarity_pairs,
    _normalized_similarity_pairs,
    _snapshot_count_declares_zero,
    _snapshot_data_view_ids,
    _snapshot_data_view_ids_cover_snapshot,
    _snapshot_data_view_names,
    _snapshot_declares_data_view_total,
    _snapshot_declares_zero_data_views,
    _snapshot_effective_data_view_total,
    _snapshot_has_ambiguous_data_view_identifiers,
    _snapshot_reported_data_view_total,
)
from cja_auto_sdr.output.sdr import (
    write_csv_output,
    write_excel_output,
    write_html_output,
    write_json_output,
    write_markdown_output,
)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_remaining_gap_coverage_pass2")


def _make_analyzer(
    logger: logging.Logger,
    *,
    config: OrgReportConfig | None = None,
) -> OrgComponentAnalyzer:
    cfg = config or OrgReportConfig(skip_lock=True, cja_per_thread=False)
    return OrgComponentAnalyzer(Mock(), cfg, logger, org_id="unit@AdobeOrg")


def _install_fake_scipy(
    monkeypatch: pytest.MonkeyPatch,
    *,
    labels: list[int],
    linkage_side_effect: Exception | None = None,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def squareform(matrix):
        captured["matrix"] = matrix.copy()
        return "condensed"

    def linkage(condensed_dist, method):
        captured["condensed_dist"] = condensed_dist
        captured["method"] = method
        if linkage_side_effect is not None:
            raise linkage_side_effect
        return "linkage-matrix"

    def fcluster(linkage_matrix, t, criterion):
        captured["linkage_matrix"] = linkage_matrix
        captured["threshold"] = t
        captured["criterion"] = criterion
        return labels

    scipy_module = types.ModuleType("scipy")
    cluster_module = types.ModuleType("scipy.cluster")
    hierarchy_module = types.ModuleType("scipy.cluster.hierarchy")
    spatial_module = types.ModuleType("scipy.spatial")
    distance_module = types.ModuleType("scipy.spatial.distance")

    hierarchy_module.linkage = linkage
    hierarchy_module.fcluster = fcluster
    distance_module.squareform = squareform

    cluster_module.hierarchy = hierarchy_module
    spatial_module.distance = distance_module
    scipy_module.cluster = cluster_module
    scipy_module.spatial = spatial_module

    monkeypatch.setitem(sys.modules, "scipy", scipy_module)
    monkeypatch.setitem(sys.modules, "scipy.cluster", cluster_module)
    monkeypatch.setitem(sys.modules, "scipy.cluster.hierarchy", hierarchy_module)
    monkeypatch.setitem(sys.modules, "scipy.spatial", spatial_module)
    monkeypatch.setitem(sys.modules, "scipy.spatial.distance", distance_module)

    return captured


class _DummyExcelWriter:
    def __init__(self) -> None:
        self.book = object()

    def __enter__(self) -> _DummyExcelWriter:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_compute_clusters_with_fake_scipy_covers_cluster_building(
    logger: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyzer = _make_analyzer(
        logger,
        config=OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True),
    )
    captured = _install_fake_scipy(monkeypatch, labels=[1, 1, 2])
    summaries = [
        DataViewSummary(data_view_id="dv1", data_view_name="Prod East"),
        DataViewSummary(data_view_id="dv2", data_view_name="Prod West"),
        DataViewSummary(data_view_id="dv3", data_view_name="Sandbox"),
    ]
    pairwise = {
        (0, 1): 0.9,
        (0, 2): 0.1,
        (1, 2): 0.2,
    }

    clusters = analyzer._compute_clusters(summaries, precomputed=(summaries, pairwise))

    assert clusters is not None
    assert [cluster.size for cluster in clusters] == [2, 1]
    assert clusters[0].cluster_name == "Prod"
    assert clusters[0].cohesion_score == 0.9
    assert captured["method"] == "average"
    matrix = captured["matrix"]
    assert float(matrix[0, 1]) == pytest.approx(0.1)
    assert float(matrix[1, 2]) == pytest.approx(0.8)
    assert captured["criterion"] == "distance"


def test_compute_clusters_fake_scipy_handles_small_inputs_and_linkage_errors(
    logger: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    analyzer = _make_analyzer(
        logger,
        config=OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True),
    )

    _install_fake_scipy(monkeypatch, labels=[1])
    with caplog.at_level(logging.INFO):
        assert analyzer._compute_clusters([DataViewSummary(data_view_id="dv1", data_view_name="Only")]) is None
    assert "Not enough data views for clustering" in caplog.text

    _install_fake_scipy(monkeypatch, labels=[1, 1], linkage_side_effect=ValueError("fake linkage failure"))
    pairwise = {(0, 1): 0.8}
    summaries = [
        DataViewSummary(data_view_id="dv1", data_view_name="One"),
        DataViewSummary(data_view_id="dv2", data_view_name="Two"),
    ]
    with caplog.at_level(logging.WARNING):
        assert analyzer._compute_clusters(summaries, precomputed=(summaries, pairwise)) is None
    assert "Clustering failed: fake linkage failure" in caplog.text


def test_run_analysis_impl_logs_cluster_count_and_exposes_lock_backend(
    logger: logging.Logger,
    caplog: pytest.LogCaptureFixture,
) -> None:
    analyzer = _make_analyzer(
        logger,
        config=OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True, skip_similarity=True),
    )
    analyzer._lock_runtime_state.backend = "file"
    summaries = [
        DataViewSummary(data_view_id="dv1", data_view_name="Prod East"),
        DataViewSummary(data_view_id="dv2", data_view_name="Prod West"),
    ]
    clusters = [
        DataViewCluster(
            cluster_id=1,
            cluster_name="Prod",
            data_view_ids=["dv1", "dv2"],
            data_view_names=["Prod East", "Prod West"],
            cohesion_score=0.9,
        ),
    ]

    with (
        patch.object(analyzer, "_assert_lock_healthy"),
        patch.object(analyzer, "_list_and_filter_data_views", return_value=([{"id": "dv1"}, {"id": "dv2"}], False, 2)),
        patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
        patch.object(analyzer, "_build_component_index", return_value={}),
        patch.object(analyzer, "_check_memory_warning"),
        patch.object(analyzer, "_compute_distribution", return_value=ComponentDistribution()),
        patch.object(analyzer, "_compute_pairwise_jaccard", return_value=(summaries, {(0, 1): 0.9})),
        patch.object(analyzer, "_compute_clusters", return_value=clusters) as compute_clusters,
        patch.object(analyzer, "_generate_recommendations", return_value=[]),
        caplog.at_level(logging.INFO),
    ):
        result = analyzer._run_analysis_impl()

    assert analyzer.last_lock_backend == "file"
    assert result.clusters == clusters
    compute_clusters.assert_called_once_with(summaries, precomputed=(summaries, {(0, 1): 0.9}))
    assert "Found 1 clusters" in caplog.text


def test_discovery_lookup_helpers_cover_remaining_edge_paths() -> None:
    recursive_items: list[object] = []
    recursive_items.append(recursive_items)

    assert _lookup_value_has_substance(()) is False
    assert _lookup_value_has_substance(recursive_items) is False
    assert _has_minimum_dataview_lookup_metadata({"id": "dv1", "future_metadata": {"owner": "alice"}}) is True
    assert _is_truthy_marker(2) is True
    assert _is_truthy_marker(0) is False

    class _EmptyRecordsFrame(pd.DataFrame):
        @property
        def _constructor(self):
            return _EmptyRecordsFrame

        def to_dict(self, orient="dict", *args, **kwargs):
            if orient == "records":
                return []
            return super().to_dict(orient=orient, *args, **kwargs)

    payload, raw_type, reason = _normalize_dataview_lookup_payload(_EmptyRecordsFrame({"id": ["dv1"]}))
    assert payload is None
    assert raw_type == "_EmptyRecordsFrame"
    assert reason == "empty_dataframe_records"

    class _BadBytes(bytes):
        def decode(self, *args, **kwargs):
            raise TypeError("bad decode")

    assert _coerce_lookup_scalar_text(_BadBytes(b"dv1")) is None
    assert _coerce_lookup_scalar_text(7) == "7"
    assert _assess_expected_lookup_id({"id": "   "}, expected_data_view_id="dv1") == (None, "missing_expected_id")
    assert (
        _is_legacy_unknown_lookup_placeholder(
            expected_data_view_id="dv1",
            normalized_items={"id": "dv_other", "name": "Unknown"},
        )
        is False
    )
    assert _unknown_placeholder_diagnostic_key({"lookup_failed": True}) == "lookup_failed"
    assert _unknown_placeholder_diagnostic_key({"lookup_failure_reason": "timeout"}) == "lookup_failure_reason"
    assert _unknown_placeholder_diagnostic_key({"lookup_debug": "detail"}) == "lookup_debug"
    assert _unknown_lookup_placeholder_reason("dv1", {"id": "dv_other", "name": "Unknown"}) is None


def test_org_model_helpers_cover_manual_snapshot_fallbacks() -> None:
    assert (
        _has_complete_data_view_ids(
            OrgReportComparisonInput(timestamp="now", has_data_view_ids=True, complete_data_view_ids=None),
        )
        is True
    )
    assert (
        _has_complete_data_view_ids(
            OrgReportComparisonInput(timestamp="now", has_data_view_ids=True, complete_data_view_ids=False),
        )
        is False
    )
    assert _has_complete_high_similarity_pairs(OrgReportComparisonInput(timestamp="now")) is False
    assert _normalized_similarity_pairs(
        {
            (" dv1 ", "dv2"),
            ("", "dv3"),
            ("dv1", " "),
            ("dv1",),
            ("dv1", "dv2", "dv3"),
        },
    ) == {("dv1", "dv2")}

    named_snapshot = TrendingSnapshot(
        timestamp="2026-03-19T00:00:00Z",
        dv_names={" dv1 ": "Primary", " ": "Ignored", "dv2": "Secondary"},
    )
    assert _snapshot_data_view_ids(named_snapshot) == {"dv1", "dv2"}
    assert _snapshot_data_view_names(
        named_snapshot,
        authoritative_ids={"dv1"},
        restrict_to_authoritative_ids=True,
    ) == {"dv1": "Primary"}

    ambiguous_snapshot = TrendingSnapshot(
        timestamp="2026-03-19T00:00:00Z",
        dv_names={"dv1": "A", " dv1 ": "B"},
    )
    assert _snapshot_has_ambiguous_data_view_identifiers(ambiguous_snapshot) is True

    raw_total_snapshot = SimpleNamespace(data_view_count="3")
    raw_zero_snapshot = SimpleNamespace(data_view_count="0")
    assert _snapshot_declares_data_view_total(raw_total_snapshot) is True
    assert _snapshot_declares_zero_data_views(raw_zero_snapshot) is True
    assert _snapshot_reported_data_view_total(raw_total_snapshot) == 3
    assert _snapshot_count_declares_zero(False) is False
    assert _snapshot_count_declares_zero("0") is True

    incomplete_snapshot = TrendingSnapshot(
        timestamp="2026-03-19T00:00:00Z",
        data_view_count=3,
        dv_ids={"dv1", "dv2"},
    )
    assert _snapshot_data_view_ids_cover_snapshot(incomplete_snapshot, {"dv1", "dv2"}) is False
    assert (
        _snapshot_effective_data_view_total(
            incomplete_snapshot,
            {"dv1", "dv2"},
            ambiguous_identifiers=False,
            complete_data_view_ids=None,
        )
        == 3
    )


def test_output_writer_branches_cover_remaining_value_and_attribute_errors(
    logger: logging.Logger,
    tmp_path: Path,
) -> None:
    data = {"Sheet1": pd.DataFrame({"value": [1]})}

    with (
        patch("cja_auto_sdr.output.sdr.pd.ExcelWriter", return_value=_DummyExcelWriter()),
        patch("cja_auto_sdr.output.sdr.apply_excel_formatting", side_effect=KeyError("missing column")),
        pytest.raises(KeyError, match="missing column"),
    ):
        write_excel_output(data, "excel", str(tmp_path), logger)

    with (
        patch.object(pd.DataFrame, "to_csv", side_effect=ValueError("bad csv")),
        pytest.raises(ValueError, match="bad csv"),
    ):
        write_csv_output(data, "csv", str(tmp_path), logger)

    with (
        patch.object(pd.DataFrame, "to_dict", side_effect=AttributeError("missing to_dict")),
        pytest.raises(AttributeError, match="missing to_dict"),
    ):
        write_json_output(data, {"Generated At": "2026-03-19"}, "json", str(tmp_path), logger)

    html_table = """
<table>
  <thead><tr><th>Issue</th><th>Severity</th></tr></thead>
  <tbody>
    <tr class="existing"><td>A</td><td>CRITICAL</td></tr>
    <tr><td>B</td><td>HIGH</td></tr>
    <tr><td>extra</td><td>ignored</td></tr>
  </tbody>
</table>
"""
    quality_df = pd.DataFrame({"Issue": ["A", "B"], "Severity": ["critical", "high"]})
    with patch.object(pd.DataFrame, "to_html", return_value=html_table):
        html_path = write_html_output(
            {"Data Quality": quality_df},
            {"Generated At": "2026-03-19"},
            "html",
            str(tmp_path),
            logger,
        )
    html_content = Path(html_path).read_text(encoding="utf-8")
    assert 'class="existing severity-CRITICAL"' in html_content
    assert 'class="severity-HIGH"' in html_content

    with (
        patch.object(pd.DataFrame, "to_html", side_effect=ValueError("bad html")),
        pytest.raises(ValueError, match="bad html"),
    ):
        write_html_output(
            {"Data Quality": quality_df}, {"Generated At": "2026-03-19"}, "html_err", str(tmp_path), logger
        )

    with (
        patch.object(pd.DataFrame, "apply", side_effect=TypeError("bad markdown")),
        pytest.raises(TypeError, match="bad markdown"),
    ):
        write_markdown_output(data, {"Generated At": "2026-03-19"}, "md", str(tmp_path), logger)


def test_main_fast_path_helpers_cover_remaining_scanner_and_policy_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "cja_auto_sdr.__main__._fast_path_option_spec",
        lambda: (
            frozenset({"--version"}),
            {
                "-q": _OptionSpec(dest="quiet", min_arity=0, accepts_inline_value=False),
                "-p": _OptionSpec(dest="profile", min_arity=1, accepts_inline_value=True),
            },
        ),
    )

    with patch(
        "cja_auto_sdr.__main__._resolve_long_option_token",
        return_value=SimpleNamespace(is_ambiguous=False, canonical_option="--version"),
    ):
        assert _scan_option_tokens(["--ver"]) == _OptionScanResult(options=(), has_parse_error=False)

    assert _scan_option_tokens(["-qx"]) == _OptionScanResult(options=("-q",), has_parse_error=False)
    assert _scan_option_tokens(["-pVALUE"]) == _OptionScanResult(options=("-p",), has_parse_error=False)
    assert _scan_option_tokens(["-q=value"]).has_parse_error is True

    with patch("cja_auto_sdr.__main__._fast_path_option_spec", return_value=(frozenset(), {})):
        assert _primary_fast_path_option_dest("--missing") is None

    with patch(
        "cja_auto_sdr.__main__._fast_path_option_spec",
        return_value=(frozenset(), {"--version": _OptionSpec(dest="version", min_arity=0, accepts_inline_value=False)}),
    ):
        assert _fast_path_allowed_option_dests("--version") == frozenset({"version"})

    with patch("cja_auto_sdr.__main__._fast_path_allowed_option_dests", return_value=frozenset()):
        assert _fast_path_options_fit_policy(("--exit-codes",), "--exit-codes") is False

    scan = _OptionScanResult(options=(_COMPLETION_OPTION,), has_parse_error=False)
    assert _resolve_non_version_fast_path_request(scan, None) is None

    namespace = SimpleNamespace(explain_exit_code=None, exit_codes=False, completion="bash", data_views=[])
    with patch("cja_auto_sdr.__main__._fast_path_options_fit_policy", return_value=False):
        assert _resolve_non_version_fast_path_request(scan, namespace) is None


def test_main_module_invocation_executes_main_guard(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["cja_auto_sdr", "--version"])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("cja_auto_sdr.__main__", run_name="__main__")

    assert exc_info.value.code == 0
    assert "cja_auto_sdr" in capsys.readouterr().out
