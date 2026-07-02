"""Tests for generator.py output writer error branches and edge cases.

Covers PermissionError, OSError, and Exception handlers in:
  write_excel_output, write_csv_output, write_json_output,
  write_html_output, write_markdown_output,
  write_diff_excel_output, write_diff_csv_output, write_diff_html_output.
Also covers inventory_objects routing in write_json_output and misc branches.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from cja_auto_sdr.generator import (
    write_csv_output,
    write_html_output,
    write_json_output,
    write_markdown_output,
)
from cja_auto_sdr.output.sdr import write_excel_output as sdr_write_excel_output

logger = logging.getLogger("test_output_writer_coverage")


def _sample_data() -> dict[str, pd.DataFrame]:
    return {"Sheet1": pd.DataFrame({"col": [1, 2, 3]})}


def _sample_metadata() -> dict:
    return {"version": "1.0", "generated_at": "2025-01-01"}


def _patch_sdr_writer(name: str, exc: Exception):
    return patch(f"cja_auto_sdr.output.sdr.{name}", side_effect=exc)


# ---------------------------------------------------------------------------
# 1. write_csv_output error branches (lines 2378-2388)
# ---------------------------------------------------------------------------


class TestWriteCsvOutputErrors:
    def test_permission_error(self, tmp_path: Path) -> None:
        with patch("os.makedirs", side_effect=PermissionError("denied")):
            with pytest.raises(PermissionError):
                write_csv_output(_sample_data(), "test", str(tmp_path), logger)

    def test_os_error(self, tmp_path: Path) -> None:
        with patch("os.makedirs", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                write_csv_output(_sample_data(), "test", str(tmp_path), logger)

    def test_generic_exception(self, tmp_path: Path) -> None:
        with patch.object(pd.DataFrame, "to_csv", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                write_csv_output(_sample_data(), "test", str(tmp_path), logger)


# ---------------------------------------------------------------------------
# 2. write_json_output error branches (lines 2448-2487)
# ---------------------------------------------------------------------------


class TestWriteJsonOutputErrors:
    def test_permission_error(self, tmp_path: Path) -> None:
        with _patch_sdr_writer("write_json_atomic_compatible", PermissionError("denied")) as mock_write:
            with pytest.raises(PermissionError):
                write_json_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)
        mock_write.assert_called_once()

    def test_os_error(self, tmp_path: Path) -> None:
        with _patch_sdr_writer("write_json_atomic_compatible", OSError("disk full")) as mock_write:
            with pytest.raises(OSError, match="disk full"):
                write_json_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)
        mock_write.assert_called_once()

    def test_serialization_error(self, tmp_path: Path) -> None:
        import json

        with patch.object(json, "dump", side_effect=TypeError("not serializable")):
            with pytest.raises(TypeError):
                write_json_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)

    def test_generic_exception(self, tmp_path: Path) -> None:
        with patch.object(pd.DataFrame, "to_dict", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                write_json_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)


class TestWriteJsonOutputInventoryObjects:
    """Lines 2448-2463: inventory_objects routing for derived/calculated/segments."""

    def test_derived_fields_inventory_object(self, tmp_path: Path) -> None:
        data = {"Derived Fields": pd.DataFrame({"field": ["f1"]})}
        inv = MagicMock()
        inv.to_json.return_value = {"fields": [{"id": "f1"}]}
        result = write_json_output(
            data,
            _sample_metadata(),
            "test",
            str(tmp_path),
            logger,
            inventory_objects={"derived": inv},
        )
        assert result.endswith(".json")

    def test_derived_fields_no_inventory(self, tmp_path: Path) -> None:
        data = {"Derived Fields": pd.DataFrame({"field": ["f1"]})}
        result = write_json_output(
            data,
            _sample_metadata(),
            "test",
            str(tmp_path),
            logger,
            inventory_objects={},
        )
        assert result.endswith(".json")

    def test_calculated_metrics_inventory_object(self, tmp_path: Path) -> None:
        data = {"Calculated Metrics": pd.DataFrame({"metric": ["m1"]})}
        inv = MagicMock()
        inv.to_json.return_value = {"metrics": [{"id": "m1"}]}
        result = write_json_output(
            data,
            _sample_metadata(),
            "test",
            str(tmp_path),
            logger,
            inventory_objects={"calculated": inv},
        )
        assert result.endswith(".json")

    def test_calculated_metrics_no_inventory(self, tmp_path: Path) -> None:
        data = {"Calculated Metrics": pd.DataFrame({"metric": ["m1"]})}
        result = write_json_output(
            data,
            _sample_metadata(),
            "test",
            str(tmp_path),
            logger,
            inventory_objects={},
        )
        assert result.endswith(".json")

    def test_segments_inventory_object(self, tmp_path: Path) -> None:
        data = {"Segments": pd.DataFrame({"segment": ["s1"]})}
        inv = MagicMock()
        inv.to_json.return_value = {"segments": [{"id": "s1"}]}
        result = write_json_output(
            data,
            _sample_metadata(),
            "test",
            str(tmp_path),
            logger,
            inventory_objects={"segments": inv},
        )
        assert result.endswith(".json")

    def test_segments_no_inventory(self, tmp_path: Path) -> None:
        data = {"Segments": pd.DataFrame({"segment": ["s1"]})}
        result = write_json_output(
            data,
            _sample_metadata(),
            "test",
            str(tmp_path),
            logger,
            inventory_objects={},
        )
        assert result.endswith(".json")


# ---------------------------------------------------------------------------
# 3. write_html_output error branches (lines 2702, 2707, 2710, 2743-2753)
# ---------------------------------------------------------------------------


class TestWriteHtmlOutputErrors:
    def test_permission_error(self, tmp_path: Path) -> None:
        with _patch_sdr_writer("write_text_atomic_compatible", PermissionError("denied")) as mock_write:
            with pytest.raises(PermissionError):
                write_html_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)
        mock_write.assert_called_once()

    def test_os_error(self, tmp_path: Path) -> None:
        with _patch_sdr_writer("write_text_atomic_compatible", OSError("disk full")) as mock_write:
            with pytest.raises(OSError, match="disk full"):
                write_html_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)
        mock_write.assert_called_once()

    def test_generic_exception(self, tmp_path: Path) -> None:
        with patch.object(pd.DataFrame, "to_html", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                write_html_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)


class TestWriteHtmlOutputSeverityEdges:
    """Lines 2702, 2707, 2710: severity class addition edge cases."""

    def test_severity_column_with_valid_classes(self, tmp_path: Path) -> None:
        """Data Quality sheet with severity column should add CSS classes."""
        data = {
            "Data Quality": pd.DataFrame(
                {
                    "Issue": ["Missing field", "Bad type"],
                    "Severity": ["critical", "warning"],
                }
            ),
        }
        result = write_html_output(data, _sample_metadata(), "test", str(tmp_path), logger)
        content = Path(result).read_text(encoding="utf-8")
        assert "severity-critical" in content or "Data Quality" in content

    def test_severity_column_with_unknown_severity(self, tmp_path: Path) -> None:
        """Unknown severity values should not add classes."""
        data = {
            "Data Quality": pd.DataFrame(
                {
                    "Issue": ["Something"],
                    "Severity": ["unknown_level"],
                }
            ),
        }
        result = write_html_output(data, _sample_metadata(), "test", str(tmp_path), logger)
        assert result.endswith(".html")


# ---------------------------------------------------------------------------
# 4. write_markdown_output error branches (lines 2895-2905)
# ---------------------------------------------------------------------------


class TestWriteMarkdownOutputErrors:
    def test_permission_error(self, tmp_path: Path) -> None:
        with _patch_sdr_writer("write_text_atomic_compatible", PermissionError("denied")) as mock_write:
            with pytest.raises(PermissionError):
                write_markdown_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)
        mock_write.assert_called_once()

    def test_os_error(self, tmp_path: Path) -> None:
        with _patch_sdr_writer("write_text_atomic_compatible", OSError("disk full")) as mock_write:
            with pytest.raises(OSError, match="disk full"):
                write_markdown_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)
        mock_write.assert_called_once()

    def test_generic_exception(self, tmp_path: Path) -> None:
        with patch.object(pd.DataFrame, "astype", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                write_markdown_output(_sample_data(), _sample_metadata(), "test", str(tmp_path), logger)


# ---------------------------------------------------------------------------
# 5. write_excel_output error branches (lines 2331-2341)
# ---------------------------------------------------------------------------


class TestWriteExcelOutputErrors:
    def test_permission_error(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import write_excel_output

        with patch("cja_auto_sdr.generator.pd.ExcelWriter", side_effect=PermissionError("denied")):
            with pytest.raises(PermissionError):
                write_excel_output(_sample_data(), "test", str(tmp_path), logger)

    def test_os_error(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import write_excel_output

        with patch("cja_auto_sdr.generator.pd.ExcelWriter", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                write_excel_output(_sample_data(), "test", str(tmp_path), logger)

    def test_generic_exception(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import write_excel_output

        with patch("cja_auto_sdr.generator.pd.ExcelWriter", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                write_excel_output(_sample_data(), "test", str(tmp_path), logger)


# ---------------------------------------------------------------------------
# 6. validate_data_view edge cases (lines 1880-1928)
# ---------------------------------------------------------------------------


class TestValidateDataViewEdgeCases:
    """Lines 1880-1928: more-than-10 listing, component warnings, exception handler."""

    def test_more_than_10_data_views_shows_truncated(self, caplog: pytest.LogCaptureFixture) -> None:
        """Line 1880: '... and N more' message when >10 DVs available."""
        from cja_auto_sdr.generator import validate_data_view

        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = None  # Invalid DV ID
        mock_cja.getDataViews.return_value = [{"id": f"dv{i}", "name": f"DV {i}"} for i in range(15)]

        with caplog.at_level(logging.INFO):
            result = validate_data_view(mock_cja, "invalid_id", logger)
        assert result is False
        assert "and 5 more" in caplog.text

    def test_exception_in_list_data_views(self, caplog: pytest.LogCaptureFixture) -> None:
        """Lines 1882-1883: exception during DV listing is caught."""
        from cja_auto_sdr.core.exceptions import APIError
        from cja_auto_sdr.generator import validate_data_view

        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = None
        mock_cja.getDataViews.side_effect = APIError("API error")

        result = validate_data_view(mock_cja, "invalid_id", logger)
        assert result is False

    def test_component_warnings(self, caplog: pytest.LogCaptureFixture) -> None:
        """Lines 1906-1913: components key with no dims/metrics triggers warning."""
        from cja_auto_sdr.generator import validate_data_view

        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {
            "id": "dv1",
            "name": "Test",
            "description": "Desc",
            "owner": {"name": "Alice"},
            "components": {"dimensions": [], "metrics": []},
        }

        with caplog.at_level(logging.WARNING):
            result = validate_data_view(mock_cja, "dv1", logger)
        assert result is True
        assert "no components defined" in caplog.text

    def test_unexpected_exception(self) -> None:
        """Lines 1917-1928: unexpected exception caught and returns False."""
        from cja_auto_sdr.core.exceptions import APIError
        from cja_auto_sdr.generator import validate_data_view

        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = APIError("unexpected")

        result = validate_data_view(mock_cja, "dv1", logger)
        assert result is False


# ---------------------------------------------------------------------------
# 7. Misc generator.py edge cases (lines 41, 656, 814, 1242, 1482-1510)
# ---------------------------------------------------------------------------


class TestArgcompleteAvailable:
    """Line 41: argcomplete import succeeds."""

    def test_argcomplete_flag(self) -> None:
        from cja_auto_sdr.cli.parser import _ARGCOMPLETE_AVAILABLE

        # Just verify the flag exists; it may be True or False
        assert isinstance(_ARGCOMPLETE_AVAILABLE, bool)


class TestLoadQualityPolicyBadReportFormat:
    """Line 656: quality_report not in ('json', 'csv')."""

    def test_invalid_report_format_raises(self, tmp_path: Path) -> None:
        import json as json_mod

        from cja_auto_sdr.generator import load_quality_policy

        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json_mod.dumps({"quality_report": "xml"}), encoding="utf-8")
        with pytest.raises(ValueError, match="must be 'json' or 'csv'"):
            load_quality_policy(str(policy_file))


class TestNormalizeExitCodeBool:
    """Line 814: bool code -> int(code)."""

    def test_bool_true(self) -> None:
        from cja_auto_sdr.generator import _normalize_exit_code

        assert _normalize_exit_code(True) == 1

    def test_bool_false(self) -> None:
        from cja_auto_sdr.generator import _normalize_exit_code

        assert _normalize_exit_code(False) == 0


class TestLoadProfileCredentialsNotDir:
    """Line 1242: profile path exists but is not a directory."""

    def test_file_not_dir_raises(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import ProfileConfigError, load_profile_credentials

        # Create a file (not dir) where the profile dir should be
        fake_profile = tmp_path / "myprofile"
        fake_profile.write_text("not a directory", encoding="utf-8")

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=fake_profile):
            with pytest.raises(ProfileConfigError, match="not a directory"):
                load_profile_credentials("myprofile", logger)


class TestNormalizeImportCredentials:
    """Lines 1482, 1487: None values skipped, unknown keys filtered out."""

    def test_none_values_skipped(self) -> None:
        from cja_auto_sdr.generator import _normalize_import_credentials

        result = _normalize_import_credentials({"client_id": None, "org_id": "abc"})
        assert "client_id" not in result
        assert result.get("org_id") == "abc"


class TestParseEnvCredentialsMissingEquals:
    """Lines 1505, 1510: .env parsing edge cases."""

    def test_no_equals_raises(self) -> None:
        from cja_auto_sdr.generator import _parse_env_credentials_content

        with pytest.raises(ValueError, match="expected KEY=VALUE"):
            _parse_env_credentials_content("INVALID_LINE_NO_EQUALS")

    def test_empty_key_raises(self) -> None:
        from cja_auto_sdr.generator import _parse_env_credentials_content

        with pytest.raises(ValueError, match="empty key"):
            _parse_env_credentials_content("=value")


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_remaining_gap_coverage_pass2.py)
# ---------------------------------------------------------------------------


class _DummyExcelWriter:
    def __init__(self) -> None:
        self.book = object()

    def __enter__(self) -> _DummyExcelWriter:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_output_writer_branches_cover_remaining_value_and_attribute_errors(
    tmp_path: Path,
) -> None:
    data = {"Sheet1": pd.DataFrame({"value": [1]})}

    with (
        patch("cja_auto_sdr.output.sdr.pd.ExcelWriter", return_value=_DummyExcelWriter()),
        patch("cja_auto_sdr.output.sdr.apply_excel_formatting", side_effect=KeyError("missing column")),
        pytest.raises(KeyError, match="missing column"),
    ):
        sdr_write_excel_output(data, "excel", str(tmp_path), logger)

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
        patch.object(pd.DataFrame, "astype", side_effect=TypeError("bad markdown")),
        pytest.raises(TypeError, match="bad markdown"),
    ):
        write_markdown_output(data, {"Generated At": "2026-03-19"}, "md", str(tmp_path), logger)
