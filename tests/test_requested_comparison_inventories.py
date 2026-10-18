"""Requested comparison evidence must distinguish unavailable from collected-empty."""

import builtins
import json
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.diff.comparator import DataViewComparator
from cja_auto_sdr.diff.models import ChangeType, DataViewSnapshot
from cja_auto_sdr.diff.snapshot import SnapshotManager

INVENTORIES = [
    ("segments_inventory", "include_segments", "segments", "SegmentsInventoryBuilder", "segment_id", "segments"),
    (
        "calculated_metrics_inventory",
        "include_calc_metrics",
        "calculated_metrics",
        "CalculatedMetricsInventoryBuilder",
        "metric_id",
        "calculated metrics",
    ),
]


@pytest.mark.parametrize(("field", "flag", "module", "builder", "id_key", "label"), INVENTORIES)
@pytest.mark.parametrize(
    ("source_state", "target_state"),
    [(None, "populated"), ("populated", None), (None, None), ([], []), ("populated", [])],
)
def test_requested_inventory_evidence(field, flag, module, builder, id_key, label, source_state, target_state):
    def snapshot(state):
        items = [{id_key: "item_1", "name": "Example"}] if state == "populated" else state
        return DataViewSnapshot(data_view_id="dv_test", data_view_name="Test", **{field: items})

    comparator = DataViewComparator(**{flag: True})
    source, target = snapshot(source_state), snapshot(target_state)
    if source_state is None or target_state is None:
        side = "source" if source_state is None else "target"
        with pytest.raises(ValueError, match=rf"(?i){side}.*{label}|{label}.*{side}"):
            comparator.compare(source, target)
    else:
        result = comparator.compare(source, target)
        diffs = result.segments_diffs if module == "segments" else result.calc_metrics_diffs
        assert [item.change_type for item in diffs] == ([ChangeType.REMOVED] if source_state == "populated" else [])
        assert result.summary.has_changes == (source_state == "populated")


@pytest.mark.parametrize(("field", "flag", "module", "builder", "id_key", "label"), INVENTORIES)
@pytest.mark.parametrize("requested", [False, True])
def test_offline_legacy_snapshot_inventory(field, flag, module, builder, id_key, label, requested, tmp_path, capsys):
    from cja_auto_sdr.diff.commands import handle_compare_snapshots_command

    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    payload = DataViewSnapshot(data_view_id="dv_test", data_view_name="Test").to_dict()
    payload.pop(field, None)
    source.write_text(json.dumps(payload))
    target.write_text(json.dumps(payload))
    assert getattr(SnapshotManager().load_snapshot(str(source)), field) is None
    outcome = handle_compare_snapshots_command(
        str(source), str(target), quiet=True, output_format="json", output_to_stdout=True, **{flag: requested}
    )
    captured = capsys.readouterr()
    assert outcome == (not requested, False, None)
    if requested:
        assert "source" in captured.err.lower() and label in captured.err.lower()
        assert captured.out == ""
    else:
        assert json.loads(captured.out)["summary"]["total_changes"] == 0


@pytest.mark.parametrize(("field", "flag", "module", "builder", "id_key", "label"), INVENTORIES)
@pytest.mark.parametrize("error_type", [ImportError, OSError])
@pytest.mark.parametrize("flow", ["snapshot", "diff_snapshot"])
def test_requested_collection_failure_preserves_files(
    field, flag, module, builder, id_key, label, error_type, flow, tmp_path, capsys, monkeypatch
):
    from cja_auto_sdr.diff.commands import handle_diff_snapshot_command, handle_snapshot_command

    manager = SnapshotManager()
    baseline = tmp_path / "baseline.json"
    manager.save_snapshot(
        DataViewSnapshot(data_view_id="dv_test", data_view_name="Test", **{field: [{id_key: "item_1"}]}), str(baseline)
    )
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    cja = MagicMock()
    cja.getDataViews.return_value = [{"id": "dv_test", "name": "Test"}]
    cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}
    cja.getMetrics.return_value = []
    cja.getDimensions.return_value = []
    failure = error_type("requested inventory unavailable")
    module_path = f"cja_auto_sdr.inventory.{module}"
    if error_type is ImportError:
        original_import = builtins.__import__

        def fail_import(name, *args, **kwargs):
            if name == module_path:
                raise failure
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fail_import)
    else:
        monkeypatch.setattr(f"{module_path}.{builder}.build", MagicMock(side_effect=failure))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "test", None)),
        patch("cja_auto_sdr.generator.cjapy.CJA", return_value=cja),
    ):
        if flow == "snapshot":
            snapshot_flag = "include_calculated_metrics" if flag == "include_calc_metrics" else flag
            success = handle_snapshot_command("dv_test", str(baseline), quiet=True, **{snapshot_flag: True})
            assert success is False
        else:
            result = handle_diff_snapshot_command(
                "dv_test",
                str(baseline),
                quiet=True,
                output_format="json",
                output_to_stdout=True,
                auto_snapshot=True,
                auto_prune=True,
                keep_last=1,
                snapshot_dir=str(tmp_path),
                **{flag: True},
            )
            assert result == (False, False, None)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "requested inventory unavailable" in captured.err
    assert getattr(failure, "_cja_snapshot_failure_stage") == f"{module}_inventory"


@pytest.mark.parametrize(("field", "flag", "module", "builder", "id_key", "label"), INVENTORIES)
@pytest.mark.parametrize(
    ("flow", "missing_source"),
    [
        ("snapshot", False),
        ("diff_snapshot", False),
        ("compare_with_prev", False),
        ("diff_snapshot", True),
        ("compare_with_prev", True),
    ],
)
def test_cli_requested_collection_failure_exit_and_summary(
    field, flag, module, builder, id_key, label, flow, missing_source, tmp_path, capsys, monkeypatch
):
    import sys

    from cja_auto_sdr.generator import main

    baseline = tmp_path / "baseline.json"
    SnapshotManager().save_snapshot(
        DataViewSnapshot(
            data_view_id="dv_test", data_view_name="Test", **{field: None if missing_source else [{id_key: "item_1"}]}
        ),
        str(baseline),
    )
    before = baseline.read_bytes()
    summary = tmp_path / "summary.json"
    cli_flag = "--include-segments" if module == "segments" else "--include-calculated"
    args = ["cja_auto_sdr", "dv_test", cli_flag, "--agent-mode", "--run-summary-json", str(summary)]
    if flow == "snapshot":
        args += ["--snapshot", str(baseline)]
    else:
        args += ["--auto-snapshot", "--auto-prune", "--keep-last", "1", "--snapshot-dir", str(tmp_path)]
        args += ["--diff-snapshot", str(baseline)] if flow == "diff_snapshot" else ["--compare-with-prev"]
    cja = MagicMock()
    cja.getDataViews.return_value = [{"id": "dv_test", "name": "Test"}]
    cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}
    cja.getMetrics.return_value = []
    cja.getDimensions.return_value = []
    monkeypatch.setattr(sys, "argv", args)
    api_method = cja.getFilters if module == "segments" else cja.getCalculatedMetrics
    api_method.side_effect = OSError("inventory timeout")
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "test", None)),
        patch("cja_auto_sdr.generator.cjapy.CJA", return_value=cja),
        pytest.raises(SystemExit) as caught,
    ):
        main()
    assert caught.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["error_type"] == "comparison_error"
    if missing_source:
        assert "source" in error["error"] and label in error["error"]
    else:
        assert error["error"] == "inventory timeout"
    report = json.loads(summary.read_text())
    assert report["exit_code"] == 1 and report["status"] == "error"
    assert report["details"]["operation_success"] is False
    assert baseline.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {"baseline.json", "summary.json"}


@pytest.mark.parametrize(("field", "flag", "module", "builder", "id_key", "label"), INVENTORIES)
@pytest.mark.parametrize(
    ("target_state", "expected_exit", "summary_stdout"), [(None, 1, False), (None, 1, True), ([], 2, False)]
)
def test_offline_cli_unavailable_vs_empty(
    field, flag, module, builder, id_key, label, target_state, expected_exit, summary_stdout, tmp_path
):
    import subprocess
    import sys

    source, target = tmp_path / "source.json", tmp_path / "target.json"
    manager = SnapshotManager()
    manager.save_snapshot(
        DataViewSnapshot(data_view_id="dv_test", data_view_name="Test", **{field: [{id_key: "item_1"}]}), str(source)
    )
    manager.save_snapshot(
        DataViewSnapshot(data_view_id="dv_test", data_view_name="Test", **{field: target_state}), str(target)
    )
    summary = tmp_path / "summary.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cja_auto_sdr",
            "--compare-snapshots",
            str(source),
            str(target),
            "--include-segments" if module == "segments" else "--include-calculated",
            *(["--format", "json", "--quiet-diff"] if summary_stdout else ["--agent-mode"]),
            "--run-summary-json",
            "-" if summary_stdout else str(summary),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == expected_exit
    report = json.loads(completed.stdout if summary_stdout else summary.read_text())
    assert report["exit_code"] == expected_exit
    assert report["details"]["operation_success"] == (expected_exit == 2)
    if expected_exit == 1:
        if not summary_stdout:
            assert completed.stdout == ""
        error = json.loads(completed.stderr)
        assert "target" in error["error"] and label in error["error"]
        assert error["error_type"] == "comparison_error"
    else:
        assert json.loads(completed.stdout)["summary"]["total_removed"] == 1
