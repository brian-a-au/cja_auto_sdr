"""Content validation tests for output formats.

Existing output format tests primarily check file existence. These tests
validate that generated files are parseable and contain correct data — row
counts, column names, metadata accuracy, special character handling, and
cross-format consistency.
"""

import json
import logging
import os
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
import pytest

from cja_auto_sdr.generator import (
    write_csv_output,
    write_excel_output,
    write_html_output,
    write_json_output,
    write_markdown_output,
)

XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rich_data_dict():
    """Data dict with varied types, nulls, and special characters."""
    return {
        "Metadata": pd.DataFrame(
            {
                "Property": ["Generated At", "Data View ID", "Tool Version", "Total Metrics"],
                "Value": ["2025-01-15 10:30:00 PST", "dv_content_test", "3.12.12", 3],
            },
        ),
        "Data Quality": pd.DataFrame(
            [
                {
                    "Severity": "HIGH",
                    "Category": "Duplicates",
                    "Type": "Metrics",
                    "Item Name": "Revenue",
                    "Issue": "Duplicate name",
                    "Details": "Appears 2 times",
                },
                {
                    "Severity": "MEDIUM",
                    "Category": "Null Values",
                    "Type": "Dimensions",
                    "Item Name": "Region",
                    "Issue": "Missing description",
                    "Details": "1 item",
                },
                {
                    "Severity": "LOW",
                    "Category": "Missing Descriptions",
                    "Type": "Metrics",
                    "Item Name": "Bounce Rate",
                    "Issue": "No description",
                    "Details": "Consider adding",
                },
            ],
        ),
        "DataView Details": pd.DataFrame(
            {
                "Property": ["Name", "ID", "Owner"],
                "Value": ["Test DataView", "dv_content_test", "Test Owner"],
            },
        ),
        "Metrics": pd.DataFrame(
            [
                {"id": "m1", "name": "Page Views", "type": "int", "description": "Total page views"},
                {"id": "m2", "name": "Revenue", "type": "currency", "description": None},
                {"id": "m3", "name": "Bounce Rate", "type": "percent", "description": ""},
            ],
        ),
        "Dimensions": pd.DataFrame(
            [
                {"id": "d1", "name": "Page Name", "type": "string", "description": "URL path"},
                {"id": "d2", "name": "Browser", "type": "string", "description": "User agent"},
                {"id": "d3", "name": "Region", "type": "string", "description": None},
                {
                    "id": "d4",
                    "name": "OS & Device <Type>",
                    "type": "string",
                    "description": 'Contains "quotes" & <angles>',
                },
            ],
        ),
    }


@pytest.fixture
def rich_metadata_dict():
    return {
        "Generated At": "2025-01-15 10:30:00 PST",
        "Data View ID": "dv_content_test",
        "Data View Name": "Test DataView",
        "Tool Version": "3.12.12",
        "Metrics Count": "3",
        "Dimensions Count": "4",
    }


# ===================================================================
# CSV content validation
# ===================================================================


class TestCSVContentValidation:
    """Validate CSV files are parseable with correct data."""

    def test_csv_metrics_roundtrip_preserves_all_rows(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("csv_test")
        output_path = write_csv_output(rich_data_dict, "test", str(tmp_path), logger)

        metrics = pd.read_csv(os.path.join(output_path, "metrics.csv"))
        assert len(metrics) == 3
        assert list(metrics["id"]) == ["m1", "m2", "m3"]
        assert list(metrics["name"]) == ["Page Views", "Revenue", "Bounce Rate"]

    def test_csv_dimensions_roundtrip_preserves_all_rows(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("csv_test")
        output_path = write_csv_output(rich_data_dict, "test", str(tmp_path), logger)

        dims = pd.read_csv(os.path.join(output_path, "dimensions.csv"))
        assert len(dims) == 4
        assert "OS & Device <Type>" in dims["name"].values

    def test_csv_data_quality_preserves_severity_order(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("csv_test")
        output_path = write_csv_output(rich_data_dict, "test", str(tmp_path), logger)

        dq = pd.read_csv(os.path.join(output_path, "data_quality.csv"))
        assert len(dq) == 3
        assert set(dq["Severity"]) == {"HIGH", "MEDIUM", "LOW"}

    def test_csv_null_values_handled(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("csv_test")
        output_path = write_csv_output(rich_data_dict, "test", str(tmp_path), logger)

        metrics = pd.read_csv(os.path.join(output_path, "metrics.csv"))
        # Revenue has None description — should be NaN in CSV roundtrip
        revenue = metrics[metrics["id"] == "m2"]
        assert pd.isna(revenue.iloc[0]["description"])

    def test_csv_metadata_has_correct_properties(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("csv_test")
        output_path = write_csv_output(rich_data_dict, "test", str(tmp_path), logger)

        metadata = pd.read_csv(os.path.join(output_path, "metadata.csv"))
        props = list(metadata["Property"])
        assert "Generated At" in props
        assert "Data View ID" in props


# ===================================================================
# JSON content validation
# ===================================================================


class TestJSONContentValidation:
    """Validate JSON files have correct structure and data."""

    def test_json_metrics_count_and_fields(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("json_test")
        path = write_json_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path) as f:
            data = json.load(f)

        assert len(data["metrics"]) == 3
        for m in data["metrics"]:
            assert "id" in m
            assert "name" in m

    def test_json_dimensions_count_and_fields(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("json_test")
        path = write_json_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path) as f:
            data = json.load(f)

        assert len(data["dimensions"]) == 4
        dim_names = [d["name"] for d in data["dimensions"]]
        assert "Page Name" in dim_names
        assert "OS & Device <Type>" in dim_names  # Special chars preserved

    def test_json_null_preserved_not_stringified(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("json_test")
        path = write_json_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path) as f:
            data = json.load(f)

        revenue = next(m for m in data["metrics"] if m["id"] == "m2")
        # None should be preserved as JSON null, not the string "None"
        assert revenue["description"] is None or revenue["description"] == ""

    def test_json_data_quality_has_issues(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("json_test")
        path = write_json_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path) as f:
            data = json.load(f)

        assert len(data["data_quality"]) == 3
        severities = {dq["Severity"] for dq in data["data_quality"]}
        assert "HIGH" in severities

    def test_json_metadata_correct(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("json_test")
        path = write_json_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path) as f:
            data = json.load(f)

        assert data["metadata"]["Data View ID"] == "dv_content_test"
        assert data["metadata"]["Tool Version"] == "3.12.12"

    def test_json_metadata_preserves_partial_markers(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("json_test")
        metadata = dict(
            rich_metadata_dict,
            **{
                "Partial Output": "Yes",
                "Partial Reasons": "required_endpoints_failed:metrics",
            },
        )
        path = write_json_output(rich_data_dict, metadata, "test_partial", str(tmp_path), logger)

        with open(path) as f:
            data = json.load(f)

        assert data["metadata"]["Partial Output"] == "Yes"
        assert data["metadata"]["Partial Reasons"] == "required_endpoints_failed:metrics"


# ===================================================================
# HTML content validation
# ===================================================================


class TestHTMLContentValidation:
    """Validate HTML files contain correct, escaped data."""

    def test_html_special_chars_escaped_in_tables(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("html_test")
        path = write_html_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        # The dimension "OS & Device <Type>" should be escaped in HTML table
        assert "<Type>" not in content, "Unescaped angle brackets in HTML table"
        assert "&amp;" in content  # & should be escaped

    def test_html_contains_all_metric_names(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("html_test")
        path = write_html_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "Page Views" in content
        assert "Revenue" in content
        assert "Bounce Rate" in content

    def test_html_contains_all_dimension_names(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("html_test")
        path = write_html_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "Page Name" in content
        assert "Browser" in content
        assert "Region" in content

    def test_html_severity_classes_present(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("html_test")
        path = write_html_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "severity-HIGH" in content
        assert "severity-MEDIUM" in content
        assert "severity-LOW" in content

    def test_html_has_section_headings(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("html_test")
        path = write_html_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "Metadata" in content
        assert "Metrics" in content
        assert "Dimensions" in content
        assert "Data Quality" in content

    def test_html_metadata_includes_partial_markers(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("html_test")
        metadata = dict(
            rich_metadata_dict,
            **{
                "Partial Output": "Yes",
                "Partial Reasons": "required_endpoints_failed:metrics",
            },
        )
        path = write_html_output(rich_data_dict, metadata, "test_partial", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "Partial Output:" in content
        assert "required_endpoints_failed:metrics" in content


# ===================================================================
# Excel content validation
# ===================================================================


class TestExcelContentValidation:
    """Validate Excel files have correct sheets and data."""

    def _get_sheet_names(self, path):
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read("xl/workbook.xml"))
        return [s.attrib["name"] for s in root.findall("x:sheets/x:sheet", XLSX_NS)]

    def _get_shared_strings(self, path):
        with zipfile.ZipFile(path) as zf:
            if "xl/sharedStrings.xml" not in zf.namelist():
                return []
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        return ["".join(t.text or "" for t in si.findall(".//x:t", XLSX_NS)) for si in root.findall("x:si", XLSX_NS)]

    def test_excel_has_all_expected_sheets(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("excel_test")
        path = write_excel_output(rich_data_dict, "test", str(tmp_path), logger)

        sheets = self._get_sheet_names(path)
        assert "Metadata" in sheets
        assert "Data Quality" in sheets
        assert "Metrics" in sheets
        assert "Dimensions" in sheets

    def test_excel_contains_metric_names(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("excel_test")
        path = write_excel_output(rich_data_dict, "test", str(tmp_path), logger)

        strings = self._get_shared_strings(path)
        assert any("Page Views" in s for s in strings)
        assert any("Revenue" in s for s in strings)

    def test_excel_contains_dimension_names(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("excel_test")
        path = write_excel_output(rich_data_dict, "test", str(tmp_path), logger)

        strings = self._get_shared_strings(path)
        assert any("Browser" in s for s in strings)
        assert any("Region" in s for s in strings)

    def test_excel_severity_values_present(self, tmp_path, rich_data_dict):
        logger = logging.getLogger("excel_test")
        path = write_excel_output(rich_data_dict, "test", str(tmp_path), logger)

        strings = self._get_shared_strings(path)
        assert any("HIGH" in s for s in strings)
        assert any("MEDIUM" in s for s in strings)


# ===================================================================
# Markdown content validation
# ===================================================================


class TestMarkdownContentValidation:
    """Validate Markdown files have correct tables and content."""

    def test_markdown_has_metric_data_in_tables(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("md_test")
        path = write_markdown_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "Page Views" in content
        assert "Revenue" in content
        assert "Bounce Rate" in content

    def test_markdown_has_pipe_separated_tables(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("md_test")
        path = write_markdown_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        # Markdown tables use pipe separators
        pipe_lines = [line for line in content.split("\n") if "|" in line]
        assert len(pipe_lines) > 5  # Multiple table rows

    def test_markdown_has_toc(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("md_test")
        path = write_markdown_output(rich_data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "Table of Contents" in content
        assert "[Metrics]" in content
        assert "[Dimensions]" in content

    def test_markdown_escapes_pipe_in_values(self, tmp_path, rich_metadata_dict):
        """Values containing | should be escaped in markdown tables."""
        logger = logging.getLogger("md_test")
        data_dict = {
            "Metrics": pd.DataFrame(
                [{"id": "m1", "name": "Rate | Percentage", "type": "int", "description": "Has | pipe"}],
            ),
        }
        path = write_markdown_output(data_dict, rich_metadata_dict, "test", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        # Pipe inside cell values should be escaped
        assert "\\|" in content

    def test_markdown_metadata_includes_partial_markers(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("md_test")
        metadata = dict(
            rich_metadata_dict,
            **{
                "Partial Output": "Yes",
                "Partial Reasons": "required_endpoints_failed:metrics",
            },
        )
        path = write_markdown_output(rich_data_dict, metadata, "test_partial", str(tmp_path), logger)

        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "**Partial Output:** Yes" in content
        assert "**Partial Reasons:** required_endpoints_failed:metrics" in content


# ===================================================================
# Cross-format consistency
# ===================================================================


class TestCrossFormatConsistency:
    """Verify data is consistent across output formats."""

    def test_metric_count_consistent_across_csv_json(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("cross_test")

        csv_path = write_csv_output(rich_data_dict, "test_csv", str(tmp_path), logger)
        json_path = write_json_output(rich_data_dict, rich_metadata_dict, "test_json", str(tmp_path), logger)

        csv_metrics = pd.read_csv(os.path.join(csv_path, "metrics.csv"))
        with open(json_path) as f:
            json_data = json.load(f)

        assert len(csv_metrics) == len(json_data["metrics"])

    def test_dimension_count_consistent_across_csv_json(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("cross_test")

        csv_path = write_csv_output(rich_data_dict, "test_csv2", str(tmp_path), logger)
        json_path = write_json_output(rich_data_dict, rich_metadata_dict, "test_json2", str(tmp_path), logger)

        csv_dims = pd.read_csv(os.path.join(csv_path, "dimensions.csv"))
        with open(json_path) as f:
            json_data = json.load(f)

        assert len(csv_dims) == len(json_data["dimensions"])

    def test_dq_issue_count_consistent_across_csv_json(self, tmp_path, rich_data_dict, rich_metadata_dict):
        logger = logging.getLogger("cross_test")

        csv_path = write_csv_output(rich_data_dict, "test_csv3", str(tmp_path), logger)
        json_path = write_json_output(rich_data_dict, rich_metadata_dict, "test_json3", str(tmp_path), logger)

        csv_dq = pd.read_csv(os.path.join(csv_path, "data_quality.csv"))
        with open(json_path) as f:
            json_data = json.load(f)

        assert len(csv_dq) == len(json_data["data_quality"])


# ---------------------------------------------------------------------------
# Quality rule identity in exports
# ---------------------------------------------------------------------------


def _identity_dq_data_dict():
    return {
        "Data Quality": pd.DataFrame(
            [
                {
                    "Severity": "LOW",
                    "Category": "Missing Descriptions",
                    "Type": "Metrics",
                    "Item Name": "2 items",
                    "Issue": "2 items without descriptions",
                    "Details": "Items: A, B",
                    "Rule ID": "dq.missing_description.v1",
                    "Component IDs": ["a", "b"],
                    "Occurrences": 2,
                    "Unaddressable IDs": 0,
                },
            ],
        ),
    }


class TestQualityIdentityExports:
    def test_to_display_frame_joins_lists_and_does_not_mutate(self):
        from cja_auto_sdr.output.sdr import to_display_frame

        df = pd.DataFrame({"ids": [["a", "b"], []], "obj": [{"k": [1]}, [{"x": 1}]], "n": [1, 2]})
        before = df.copy(deep=True)
        out = to_display_frame(df)
        assert out["ids"].tolist() == ["a, b", ""]
        assert out["obj"][0] == json.dumps({"k": [1]}, indent=2)
        assert out["obj"][1] == json.dumps([{"x": 1}], indent=2)
        assert out["n"].tolist() == [1, 2]
        assert isinstance(df["ids"][0], list)
        assert df["obj"].tolist() == before["obj"].tolist()

    def test_to_display_frame_joins_numpy_scalars(self):
        import numpy as np

        from cja_auto_sdr.output.sdr import to_display_frame

        df = pd.DataFrame({"ids": [[np.int64(1), np.int64(2)], [pd.Timestamp("2025-01-01")]]})
        out = to_display_frame(df)
        assert out["ids"][0] == "1, 2"
        assert out["ids"][1] == "2025-01-01 00:00:00"

    def test_json_keeps_component_ids_as_list(self, tmp_path, rich_metadata_dict):
        path = write_json_output(_identity_dq_data_dict(), rich_metadata_dict, "t", str(tmp_path), logging.getLogger())
        with open(path) as f:
            data = json.load(f)
        assert data["data_quality"][0]["Component IDs"] == ["a", "b"]
        assert data["data_quality"][0]["Rule ID"] == "dq.missing_description.v1"

    def test_csv_joins_component_ids(self, tmp_path):
        out = write_csv_output(_identity_dq_data_dict(), "t", str(tmp_path), logging.getLogger())
        row = pd.read_csv(os.path.join(out, "data_quality.csv")).iloc[0]
        assert row["Component IDs"] == "a, b"
        assert row["Rule ID"] == "dq.missing_description.v1"

    def test_excel_data_quality_cell_is_joined(self, tmp_path):
        path = write_excel_output(_identity_dq_data_dict(), "t", str(tmp_path), logging.getLogger())
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        strings = ["".join(t.text or "" for t in si.findall(".//x:t", XLSX_NS)) for si in root.findall("x:si", XLSX_NS)]
        assert "Component IDs" in strings
        assert "a, b" in strings

    def test_html_and_markdown_render_joined_ids(self, tmp_path, rich_metadata_dict):
        html_path = write_html_output(
            _identity_dq_data_dict(), rich_metadata_dict, "t", str(tmp_path), logging.getLogger()
        )
        md_path = write_markdown_output(
            _identity_dq_data_dict(),
            rich_metadata_dict,
            "t",
            str(tmp_path),
            logging.getLogger(),
        )
        assert "a, b" in open(html_path).read()
        assert "| a, b |" in open(md_path).read()


# ===================================================================
# Typed SDR JSON (--json-typed)
# ===================================================================

_LEGACY_GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sdr_legacy_payload_golden.json")


class _GoldenCalculatedInventory:
    def to_json(self):
        return {"summary": {"total": 1}, "metrics": [{"id": "cm1", "complexity": 2.5}]}


def _legacy_golden_inputs():
    """Inputs whose legacy payload is pinned byte-for-byte in the golden fixture."""
    import numpy as np

    data_dict = {
        "Metadata": pd.DataFrame({"Property": ["Data View ID"], "Value": ["dv_golden"]}),
        "Data Quality": pd.DataFrame(
            [
                {
                    "Severity": "HIGH",
                    "Category": "Duplicates",
                    "Type": "Metrics",
                    "Item Name": "Revenue",
                    "Issue": "Duplicate name",
                    "Details": "Appears 2 times",
                }
            ]
        ),
        "DataView Details": pd.DataFrame({"id": ["dv_golden"], "name": ["Golden View"], "tags": ['[\n  "a"\n]']}),
        "Metrics": pd.DataFrame(
            [
                {
                    "id": "m1",
                    "name": "Page Views",
                    "precision": 0,
                    "isDeleted": False,
                    "definition": '{\n  "func": "sum"\n}',
                },
                {"id": "m2", "name": "Revenue", "precision": 2, "isDeleted": True, "definition": None},
            ]
        ),
        "Dimensions": pd.DataFrame(
            {
                "id": pd.array(["d1", "d2"], dtype="string"),
                "description": pd.array(["Browser", None], dtype="string"),
                "score": [1.5, np.nan],
            }
        ),
        "Derived Fields": pd.DataFrame(
            {"Status": ["No derived fields found for this data view"], "Data View ID": ["dv_golden"]}
        ),
        "Calculated Metrics": pd.DataFrame({"id": ["cm1"]}),
    }
    metadata = {"Data View ID": "dv_golden", "Data View Name": "Golden View", "Metrics Count": "2"}
    inventory = {"derived": None, "calculated": _GoldenCalculatedInventory(), "segments": None}
    return data_dict, metadata, inventory


_AE5_METRIC = {
    "id": "m1",
    "fieldDefinition": [{"func": "match", "cases": [1, 2]}],
    "isDeleted": True,
    "precision": 1,
    "description": '{"looks": "json"}',
    "tags": [],
    "settings": {},
    "extra": None,
}


def _typed_inputs(metric=None, data_view=None):
    metric = dict(_AE5_METRIC if metric is None else metric)
    native_metrics = pd.DataFrame([metric])
    native_dimensions = pd.DataFrame([{"id": "d1", "name": "Browser", "hasData": False, "count": 0}])
    data_dict = {
        "Metadata": pd.DataFrame({"Property": ["Data View ID"], "Value": ["dv_typed"]}),
        "Data Quality": pd.DataFrame(
            [{"Severity": "LOW", "Category": "Missing", "Type": "Metrics", "Item Name": "m1", "Issue": "x"}]
        ),
        "DataView Details": pd.DataFrame({"id": ["dv_typed"]}),
        # Display-mutated frames: the typed builder must not read these.
        "Metrics": native_metrics.map(lambda v: json.dumps(v, default=str) if isinstance(v, (list, dict)) else v),
        "Dimensions": native_dimensions.copy(),
    }
    return {
        "data_dict": data_dict,
        "native_frames": {"Metrics": native_metrics, "Dimensions": native_dimensions},
        "data_view": data_view if data_view is not None else {"id": "dv_typed", "name": "Typed"},
        "metadata_dict": {"Data View ID": "dv_typed"},
    }


class TestTypedJSONPayload:
    """AE5: typed JSON keeps native values from pre-display frames."""

    def test_typed_payload_preserves_native_types(self):
        from cja_auto_sdr.output.sdr import TYPED_SDR_SCHEMA_VERSION, build_typed_json_payload

        p = build_typed_json_payload(**_typed_inputs())
        m = p["metrics"][0]
        assert m["fieldDefinition"] == [{"func": "match", "cases": [1, 2]}]
        assert m["isDeleted"] is True
        assert m["precision"] == 1
        assert type(m["precision"]) is int
        assert m["description"] == '{"looks": "json"}'
        assert m["tags"] == []
        assert m["settings"] == {}
        assert m["extra"] is None
        d = p["dimensions"][0]
        assert d["hasData"] is False
        assert d["count"] == 0
        assert type(d["count"]) is int
        assert p["schema_version"] == "cja-auto-sdr.sdr-typed/1"
        assert TYPED_SDR_SCHEMA_VERSION == "cja-auto-sdr.sdr-typed/1"

    def test_typed_payload_key_order_and_shared_sections(self):
        from cja_auto_sdr.output.sdr import build_json_payload, build_typed_json_payload

        inputs = _typed_inputs()
        typed = build_typed_json_payload(**inputs)
        legacy = build_json_payload(inputs["data_dict"], inputs["metadata_dict"])
        assert list(typed) == ["schema_version", *legacy]
        for key in ("metadata", "data_quality", "derived_fields", "calculated_metrics", "segments"):
            assert typed[key] == legacy[key]

    def test_typed_data_view_keeps_full_lists(self):
        from cja_auto_sdr.output.sdr import build_typed_json_payload

        dv = {"id": "dv_typed", "components": ["a", "b", "c"], "settings": {"x": [1]}, "enabled": True}
        p = build_typed_json_payload(**_typed_inputs(data_view=dv))
        assert p["data_view"] == dv
        assert p["data_view"]["enabled"] is True

    def test_typed_payload_is_strict_json(self):
        import numpy as np

        from cja_auto_sdr.output.sdr import build_typed_json_payload

        metric = {
            "id": "m1",
            "score": np.nan,
            "weight": np.float64(2.5),
            "count": np.int64(3),
            "flag": np.bool_(True),
            "nested": {"a": float("nan"), "b": [pd.NA, None, float("inf")]},
            "when": pd.NaT,
        }
        p = build_typed_json_payload(**_typed_inputs(metric=metric, data_view={"id": "dv", "x": float("nan")}))
        text = json.dumps(p, allow_nan=False)
        m = json.loads(text)["metrics"][0]
        assert m["score"] is None
        assert m["weight"] == 2.5
        assert m["count"] == 3
        assert m["flag"] is True
        assert m["nested"] == {"a": None, "b": [None, None, None]}
        assert m["when"] is None
        assert p["data_view"]["x"] is None

    def test_typed_sections_absent_when_legacy_omits_them(self):
        from cja_auto_sdr.output.sdr import build_typed_json_payload

        inputs = _typed_inputs()
        inputs["data_dict"] = {"Segments": pd.DataFrame({"id": ["s1"]})}
        p = build_typed_json_payload(**inputs)
        assert p["metrics"] == []
        assert p["dimensions"] == []
        assert p["data_view"] == {}
        assert p["segments"] == {"segments": [{"id": "s1"}]}

    def test_to_native_json_rules(self):
        import numpy as np

        from cja_auto_sdr.output.sdr import to_native_json

        assert to_native_json('{"a": 1}') == '{"a": 1}'
        assert to_native_json((1, np.int32(2))) == [1, 2]
        assert type(to_native_json(np.int64(7))) is int
        assert to_native_json({"k": np.float32(0.5)}) == {"k": 0.5}
        assert to_native_json(np.array([1, 2])) == [1, 2]
        assert to_native_json(pd.Timestamp("2025-01-01T00:00:00Z")) == "2025-01-01T00:00:00+00:00"
        assert to_native_json(True) is True
        assert to_native_json(1) == 1
        assert type(to_native_json(1)) is int

    def test_legacy_payload_unchanged(self):
        from cja_auto_sdr.output.sdr import build_json_payload

        data_dict, metadata, inventory = _legacy_golden_inputs()
        text = json.dumps(build_json_payload(data_dict, metadata, inventory), indent=2, ensure_ascii=False) + "\n"
        with open(_LEGACY_GOLDEN_PATH, encoding="utf-8") as f:
            assert text == f.read()

    def test_write_typed_json_output_is_strict_and_matches_payload(self, tmp_path):
        from cja_auto_sdr.output.sdr import build_typed_json_payload, write_typed_json_output

        payload = build_typed_json_payload(**_typed_inputs())
        path = write_typed_json_output(payload, "typed", str(tmp_path), logging.getLogger("typed"))
        assert path == os.path.join(str(tmp_path), "typed.json")
        with open(path, encoding="utf-8") as f:
            assert json.load(f) == payload

    def test_write_typed_json_output_rejects_non_finite(self, tmp_path):
        from cja_auto_sdr.output.sdr import write_typed_json_output

        target = tmp_path / "bad.json"
        with pytest.raises(ValueError):
            write_typed_json_output({"x": float("nan")}, "bad", str(tmp_path), logging.getLogger("typed"))
        assert not target.exists()
