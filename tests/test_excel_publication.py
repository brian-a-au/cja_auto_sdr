"""Excel publication must preserve the last complete artifact on failure."""

import logging
from unittest.mock import Mock

import pandas as pd
import pytest

from cja_auto_sdr import generator
from cja_auto_sdr.output import sdr


@pytest.fixture
def generate(monkeypatch, tmp_path):
    logger = logging.getLogger("excel_publication")
    metrics = pd.DataFrame([{"id": "m1", "name": "Metric", "type": "int", "description": "Metric", "title": "Metric"}])
    dimensions = pd.DataFrame(
        [{"id": "d1", "name": "Dimension", "type": "string", "description": "Dimension", "title": "Dimension"}]
    )
    fetcher = Mock()
    fetcher.fetch_all_data.return_value = (
        metrics,
        dimensions,
        {"id": "dv_test", "name": "Test", "owner": {"name": "Owner"}},
    )
    monkeypatch.setattr(generator, "initialize_cja", Mock(return_value=Mock()))
    monkeypatch.setattr(generator, "ParallelAPIFetcher", Mock(return_value=fetcher))
    monkeypatch.setattr(generator, "setup_logging", Mock(return_value=logger))

    def run(entry, destination, **kwargs):
        if entry == "writer":
            return sdr.write_excel_output(
                {"Metrics": metrics, "Dimensions": dimensions}, destination.stem, destination.parent, logger
            )
        return generator.process_single_dataview(
            "dv_test", output_dir=str(tmp_path), output_file=str(destination), output_format="excel", **kwargs
        )

    return run


@pytest.mark.parametrize("entry", ["writer", "generator"])
@pytest.mark.parametrize("existing", [True, False])
def test_sheet_failure_preserves_destination(generate, monkeypatch, tmp_path, entry, existing):
    destination = tmp_path / "report.xlsx"
    if existing:
        pd.DataFrame({"original": [42]}).to_excel(destination, index=False)
    old_bytes = destination.read_bytes() if existing else None
    module = sdr if entry == "writer" else generator
    real_format = module.apply_excel_formatting

    def fail_dimensions(writer, frame, name, *args):
        if name == "Dimensions":
            raise ValueError("Dimensions rendering failed")
        return real_format(writer, frame, name, *args)

    monkeypatch.setattr(module, "apply_excel_formatting", fail_dimensions)
    if entry == "writer":
        with pytest.raises(ValueError, match="Dimensions rendering failed"):
            generate(entry, destination)
    else:
        result = generate(entry, destination)
        assert not result.success
        assert result.failure_code == "OUTPUT_WRITE_FAILED"
        assert result.output_files == []
        assert not result.output_file
    assert destination.read_bytes() == old_bytes if existing else not destination.exists()
    assert set(tmp_path.iterdir()) == ({destination} if existing else set())


@pytest.mark.parametrize("entry", ["writer", "generator"])
@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("failure", ["close", "replace", "render_and_close"])
def test_publication_failure_preserves_destination(generate, monkeypatch, tmp_path, entry, existing, failure):
    from xlsxwriter.exceptions import FileCreateError

    from cja_auto_sdr.output import excel_staging

    destination = tmp_path / "report.xlsx"
    if existing:
        pd.DataFrame({"original": [42]}).to_excel(destination, index=False)
    old_bytes = destination.read_bytes() if existing else None
    error = FileCreateError("workbook close failed") if failure != "replace" else OSError("replacement failed")

    def fail(*args, _error=error, **kwargs):
        raise _error

    if failure == "replace":
        monkeypatch.setattr(excel_staging.os, "replace", fail)
    else:
        monkeypatch.setattr(pd.ExcelWriter, "close", fail)
    if failure == "render_and_close":
        error = ValueError("original rendering failure")
        module = sdr if entry == "writer" else generator
        monkeypatch.setattr(module, "apply_excel_formatting", Mock(side_effect=error))
    if entry == "writer":
        with pytest.raises(type(error)) as caught:
            generate(entry, destination)
        assert caught.value is error
    else:
        result = generate(entry, destination)
        assert not result.success
        assert result.failure_code == "OUTPUT_WRITE_FAILED"
        assert result.error_message == str(error)
        assert result.output_files == []
    assert destination.read_bytes() == old_bytes if existing else not destination.exists()
    assert set(tmp_path.iterdir()) == ({destination} if existing else set())


@pytest.mark.parametrize("entry", ["writer", "generator"])
def test_existing_permissions_and_symlink_preserved(generate, tmp_path, entry):
    import stat

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "actual.xlsx"
    target.write_bytes(b"old workbook")
    target.chmod(0o640)
    link = tmp_path / "report.xlsx"
    link.symlink_to(target)
    result = generate(entry, link)
    assert entry == "writer" or result.success
    assert link.is_symlink()
    assert link.resolve() == target
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert target.read_bytes().startswith(b"PK")
    assert set(target_dir.iterdir()) == {target}


@pytest.mark.parametrize("entry", ["writer", "generator"])
@pytest.mark.parametrize("kind", ["hardlink", "directory", "fifo"])
def test_incompatible_destinations_are_rejected(generate, tmp_path, entry, kind):
    import os

    from cja_auto_sdr.core.exceptions import OutputError

    destination = tmp_path / "report.xlsx"
    if kind == "hardlink":
        destination.write_bytes(b"original")
        os.link(destination, tmp_path / "alias.xlsx")
    elif kind == "directory":
        destination.mkdir()
    else:
        os.mkfifo(destination)
    before = destination.stat()
    if entry == "writer":
        with pytest.raises(OutputError, match="Choose"):
            generate(entry, destination)
    else:
        result = generate(entry, destination)
        assert not result.success
        assert result.failure_code == "OUTPUT_WRITE_FAILED"
        assert "Choose" in result.error_message
    assert destination.stat() == before
    if kind == "hardlink":
        assert destination.read_bytes() == b"original"
        assert (tmp_path / "alias.xlsx").read_bytes() == b"original"
    assert not list(tmp_path.glob(".xlsx-*"))


@pytest.mark.parametrize("entry", ["writer", "generator"])
def test_long_filename_publishes(generate, tmp_path, entry):
    import os

    destination = tmp_path / ("x" * (os.pathconf(tmp_path, "PC_NAME_MAX") - 5) + ".xlsx")
    result = generate(entry, destination)
    assert entry == "writer" or result.success
    assert destination.read_bytes().startswith(b"PK")
    assert set(tmp_path.iterdir()) == {destination}


@pytest.mark.parametrize("entry", ["writer", "generator"])
def test_unwritable_directory_preserves_destination(generate, tmp_path, entry):
    import os

    if os.geteuid() == 0:
        pytest.skip("Root bypasses directory write permissions")
    directory = tmp_path / "readonly"
    directory.mkdir()
    destination = directory / "report.xlsx"
    destination.write_bytes(b"original")
    directory.chmod(0o500)
    try:
        if entry == "writer":
            with pytest.raises(PermissionError):
                generate(entry, destination)
        else:
            result = generate(entry, destination)
            assert not result.success
            assert result.failure_code == "OUTPUT_PERMISSION_DENIED"
        assert destination.read_bytes() == b"original"
        assert set(directory.iterdir()) == {destination}
    finally:
        directory.chmod(0o700)


@pytest.mark.parametrize("mask", [0o002, 0o077])
def test_new_file_respects_umask_in_subprocess(tmp_path, mask):
    import subprocess
    import sys

    code = """
import logging, os, stat, sys
import pandas as pd
from cja_auto_sdr.output.sdr import write_excel_output
os.umask(int(sys.argv[2]))
path = write_excel_output({"Metrics": pd.DataFrame({"name": ["Metric"]})}, "report", sys.argv[1], logging.getLogger())
assert stat.S_IMODE(os.stat(path).st_mode) == 0o666 & ~int(sys.argv[2])
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path), str(mask)], check=True)


def test_failed_workbook_is_not_completed_in_run_summary(generate, monkeypatch, tmp_path):
    import json
    import sys

    destination = tmp_path / "report.xlsx"
    summary = tmp_path / "summary.json"
    monkeypatch.setattr(generator, "resolve_data_view_names", Mock(return_value=(["dv_test"], {})))
    monkeypatch.setattr(generator, "apply_excel_formatting", Mock(side_effect=ValueError("render failed")))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cja_auto_sdr",
            "dv_test",
            "--format",
            "excel",
            "--output",
            str(destination),
            "--run-summary-json",
            str(summary),
        ],
    )
    with pytest.raises(SystemExit) as caught:
        generator.main()
    assert caught.value.code == 1
    payload = json.loads(summary.read_text())
    assert payload["exit_code"] == 1
    assert payload["results"][0]["failure_code"] == "OUTPUT_WRITE_FAILED"
    assert payload["results"][0]["output_files"] == []
    assert not payload["results"][0]["output_file"]
    assert not destination.exists()


@pytest.mark.parametrize(
    ("options", "components"),
    [
        ({}, ["Metrics", "Dimensions"]),
        ({"metrics_only": True}, ["Metrics"]),
        ({"dimensions_only": True}, ["Dimensions"]),
    ],
)
def test_generator_sheet_order_data_and_formatting(generate, tmp_path, options, components):
    import xml.etree.ElementTree as ET
    import zipfile

    destination = tmp_path / "report.xlsx"
    result = generate("generator", destination, **options)
    assert result.success
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(destination) as workbook:
        assert workbook.testzip() is None
        root = ET.fromstring(workbook.read("xl/workbook.xml"))
        names = [s.attrib["name"] for s in root.findall("x:sheets/x:sheet", ns)]
        assert names == ["Metadata", "Data Quality", "DataView", *components]
        strings = workbook.read("xl/sharedStrings.xml").decode()
        for name in components:
            assert name[:-1] in strings
            index = names.index(name) + 1
            sheet = ET.fromstring(workbook.read(f"xl/worksheets/sheet{index}.xml"))
            assert sheet.find("x:sheetViews/x:sheetView/x:pane", ns).attrib["state"] == "frozen"
            assert sheet.find("x:autoFilter", ns) is not None
            assert sheet.find("x:sheetData/x:row/x:c", ns).attrib.get("s")
    assert set(tmp_path.iterdir()) == {destination}


def test_generator_inventory_placeholders_and_argument_order(generate, monkeypatch, tmp_path):
    import xml.etree.ElementTree as ET
    import zipfile

    from cja_auto_sdr.inventory.calculated_metrics import CalculatedMetricsInventoryBuilder
    from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

    inventory = Mock()
    inventory.get_dataframe.return_value = pd.DataFrame()
    inventory.get_summary.return_value = {}
    monkeypatch.setattr(CalculatedMetricsInventoryBuilder, "build", Mock(return_value=inventory))
    monkeypatch.setattr(SegmentsInventoryBuilder, "build", Mock(return_value=inventory))
    destination = tmp_path / "report.xlsx"
    result = generate(
        "generator",
        destination,
        inventory_only=True,
        include_segments_inventory=True,
        include_calculated_metrics=True,
        inventory_order=["segments", "calculated"],
    )
    assert result.success
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(destination) as workbook:
        root = ET.fromstring(workbook.read("xl/workbook.xml"))
        assert [s.attrib["name"] for s in root.findall("x:sheets/x:sheet", ns)] == ["Segments", "Calculated Metrics"]
        strings = workbook.read("xl/sharedStrings.xml").decode()
        assert "No segments found for this data view" in strings
        assert "No calculated metrics found for this data view" in strings
