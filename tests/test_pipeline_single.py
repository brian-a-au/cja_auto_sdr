"""Tests for the modular single-dataview pipeline wrapper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import cja_auto_sdr.pipeline.single as pipeline_single
from cja_auto_sdr.pipeline.single import process_single_dataview


def test_process_single_dataview_accepts_legacy_positional_arguments():
    expected = object()
    fake_generator = SimpleNamespace(process_single_dataview=Mock(return_value=expected))

    with patch("cja_auto_sdr.pipeline.single._generator_module", return_value=fake_generator):
        result = process_single_dataview("dv_123", "config.json", "/tmp/output")

    assert result is expected
    fake_generator.process_single_dataview.assert_called_once_with("dv_123", "config.json", "/tmp/output")


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_small_gap_coverage.py)
# ---------------------------------------------------------------------------


def test_pipeline_single_wrapper_uses_real_generator_module_and_signature_binding() -> None:
    pipeline_single._process_single_dataview_signature.cache_clear()
    expected = object()

    try:
        with patch("cja_auto_sdr.generator.process_single_dataview", return_value=expected) as mock_process:
            result = pipeline_single.process_single_dataview("dv_1", "config.json", "/tmp/out")
    finally:
        pipeline_single._process_single_dataview_signature.cache_clear()

    assert result is expected
    mock_process.assert_called_once_with("dv_1", "config.json", "/tmp/out")
