"""Tests for the modular single-dataview pipeline wrapper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from cja_auto_sdr.pipeline.single import process_single_dataview


def test_process_single_dataview_accepts_legacy_positional_arguments():
    expected = object()
    fake_generator = SimpleNamespace(process_single_dataview=Mock(return_value=expected))

    with patch("cja_auto_sdr.pipeline.single._generator_module", return_value=fake_generator):
        result = process_single_dataview("dv_123", "config.json", "/tmp/output")

    assert result is expected
    fake_generator.process_single_dataview.assert_called_once_with("dv_123", "config.json", "/tmp/output")
