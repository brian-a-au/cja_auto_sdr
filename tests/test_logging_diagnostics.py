"""Tests for emit_diagnostic performance optimization."""

import logging as _logging

from cja_auto_sdr.core.logging import emit_diagnostic


def test_emit_diagnostic_skips_formatting_when_disabled():
    """Verify that formatting is skipped when the log level is disabled."""
    logger = _logging.getLogger("diag-test")
    logger.setLevel(_logging.ERROR)  # INFO diagnostics disabled

    class Boom:
        def __repr__(self):  # would blow up if formatted
            raise AssertionError("must not format when disabled")

    # field value passed as a keyword arg (collected into **fields); must return without formatting it.
    emit_diagnostic(logger, "x", "test", level=_logging.INFO, k=Boom())


def test_emit_diagnostic_emits_when_enabled(caplog):
    """Verify that emit_diagnostic still works when the log level is enabled."""
    logger = _logging.getLogger("diag-test-2")
    logger.setLevel(_logging.INFO)
    with caplog.at_level(_logging.INFO, logger="diag-test-2"):
        emit_diagnostic(logger, "y", "test", level=_logging.INFO, k="v")
    assert any("[DIAG] y" in r.message for r in caplog.records)
