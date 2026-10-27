"""Metadata policy, metadata change count, and coverage in HTML/CSV/Excel diff reports."""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

from cja_auto_sdr.diff.models import DiffCoverage, DiffResult, DiffSummary, MetadataDiff, coverage_rows
from cja_auto_sdr.output.diff.csv import write_diff_csv_output
from cja_auto_sdr.output.diff.excel import write_diff_excel_output
from cja_auto_sdr.output.diff.html import write_diff_html_output

logger = logging.getLogger("test_diff_report_coverage")


def _coverage(policy: str = "reported") -> DiffCoverage:
    return DiffCoverage(
        compare_fields=["name", "description"],
        ignored_fields=[],
        component_types=["metrics", "dimensions"],
        inventories=[],
        metadata_policy=policy,
        show_only=None,
        limitations=["Only listed fields compared", "<b>x</b>"],
    )


def _result(*, metadata_changes: int, include: bool, coverage: DiffCoverage | None) -> DiffResult:
    return DiffResult(
        summary=DiffSummary(metadata_changes=metadata_changes, include_metadata=include),
        metadata_diff=MetadataDiff(source_name="A", target_name="B", source_id="dv_a", target_id="dv_b"),
        metric_diffs=[],
        dimension_diffs=[],
        coverage=coverage,
    )


def _csv_rows(path: str) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["Property"]: r["Value"] for r in csv.DictReader(f)}


def _sheet_rows(path: str, name: str) -> dict[str, str]:
    ws = load_workbook(path)[name]
    return {str(r[0]): ("" if r[1] is None else str(r[1])) for r in ws.iter_rows(min_row=2, values_only=True)}


CASES = [
    (1, False, "reported"),
    (1, True, "included"),
    (0, False, "reported"),
    (0, True, "included"),
]


@pytest.mark.parametrize(("count", "include", "policy"), CASES)
def test_html_metadata_line_and_policy(tmp_path, count, include, policy):
    r = _result(metadata_changes=count, include=include, coverage=_coverage(policy))
    content = Path(write_diff_html_output(r, "d", str(tmp_path), logger)).read_text(encoding="utf-8")
    assert f"Metadata policy: {policy}" in content
    if count:
        suffix = "(counted)" if include else "(not counted; use --include-metadata-changes)"
        assert f"Metadata changes: 1 {suffix}" in content
    else:
        assert "Metadata changes:" not in content


def test_html_coverage_section(tmp_path):
    r = _result(metadata_changes=1, include=False, coverage=_coverage())
    content = Path(write_diff_html_output(r, "d", str(tmp_path), logger)).read_text(encoding="utf-8")
    assert "Comparison coverage" in content
    assert "compare_fields" in content
    assert "name, description" in content
    assert "limitations" in content
    assert "Only listed fields compared, &lt;b&gt;x&lt;/b&gt;" in content
    assert "<b>x</b>" not in content
    assert "—" in content  # show_only None / empty ignored_fields


def test_html_no_coverage(tmp_path):
    r = _result(metadata_changes=0, include=False, coverage=None)
    content = Path(write_diff_html_output(r, "d", str(tmp_path), logger)).read_text(encoding="utf-8")
    assert "Comparison coverage" not in content
    assert "Metadata policy: reported" in content


@pytest.mark.parametrize(("count", "include", "policy"), CASES)
def test_csv_metadata_rows(tmp_path, count, include, policy):
    r = _result(metadata_changes=count, include=include, coverage=_coverage(policy))
    d = write_diff_csv_output(r, "d", str(tmp_path), logger)
    rows = _csv_rows(os.path.join(d, "metadata.csv"))
    assert rows["metadata_changes"] == str(count)
    assert rows["metadata_policy"] == policy
    assert list(rows).index("metadata_changes") == list(rows).index("total_changes") + 1


def test_csv_coverage_file(tmp_path):
    r = _result(metadata_changes=1, include=False, coverage=_coverage())
    d = write_diff_csv_output(r, "d", str(tmp_path), logger)
    rows = _csv_rows(os.path.join(d, "coverage.csv"))
    assert rows["compare_fields"] == "name; description"
    assert rows["limitations"] == "Only listed fields compared; <b>x</b>"
    assert rows["metadata_policy"] == "reported"


def test_csv_no_coverage(tmp_path):
    r = _result(metadata_changes=0, include=False, coverage=None)
    d = write_diff_csv_output(r, "d", str(tmp_path), logger)
    assert not os.path.exists(os.path.join(d, "coverage.csv"))
    assert _csv_rows(os.path.join(d, "metadata.csv"))["metadata_policy"] == "reported"


@pytest.mark.parametrize(("count", "include", "policy"), CASES)
def test_excel_metadata_rows(tmp_path, count, include, policy):
    r = _result(metadata_changes=count, include=include, coverage=_coverage(policy))
    p = write_diff_excel_output(r, "d", str(tmp_path), logger)
    rows = _sheet_rows(p, "Metadata")
    assert rows["Metadata Changes"] == str(count)
    assert rows["Metadata Policy"] == policy


def test_excel_coverage_sheet(tmp_path):
    r = _result(metadata_changes=1, include=False, coverage=_coverage())
    p = write_diff_excel_output(r, "d", str(tmp_path), logger)
    wb = load_workbook(p)
    assert wb.sheetnames.index("Coverage") == wb.sheetnames.index("Metadata") + 1
    rows = _sheet_rows(p, "Coverage")
    assert rows["compare_fields"] == "name; description"
    assert "Only listed fields compared" in rows["limitations"]


def test_excel_no_coverage(tmp_path):
    r = _result(metadata_changes=0, include=False, coverage=None)
    p = write_diff_excel_output(r, "d", str(tmp_path), logger)
    wb = load_workbook(p)
    assert "Coverage" not in wb.sheetnames
    assert _sheet_rows(p, "Metadata")["Metadata Policy"] == "reported"


def test_summary_metadata_policy_property():
    assert DiffSummary().metadata_policy == "reported"
    assert DiffSummary(include_metadata=True).metadata_policy == "included"


def test_coverage_rows_helper():
    rows = dict(coverage_rows(_coverage()))
    assert rows["compare_fields"] == "name; description"
    assert rows["ignored_fields"] == ""
    assert rows["show_only"] == ""
    assert rows["metadata_policy"] == "reported"
