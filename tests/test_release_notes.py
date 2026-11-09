from __future__ import annotations

import pytest
from scripts import release_notes

CHANGELOG = """# Changelog

## [Unreleased]

## [2.0.1] - 2026-11-02

This patch fixes two bugs.

### Fixed

- **First fix:** details.
- **Second fix:** details.

## [2.0.0] - 2026-11-01

### Added

- A feature.
"""


def test_extract_notes_returns_only_the_requested_section() -> None:
    notes = release_notes.extract_notes(CHANGELOG, "2.0.1")

    assert notes.startswith("This patch fixes two bugs.")
    assert "- **Second fix:** details." in notes
    assert "2.0.0" not in notes
    assert "A feature." not in notes
    assert notes.endswith("details.\n")


def test_extract_notes_reads_the_last_section_to_the_end() -> None:
    notes = release_notes.extract_notes(CHANGELOG, "2.0.0")

    assert notes == "### Added\n\n- A feature.\n"


def test_extract_notes_does_not_match_a_version_prefix() -> None:
    with pytest.raises(release_notes.ReleaseNotesError, match=r"no section for 2\.0\b"):
        release_notes.extract_notes(CHANGELOG, "2.0")


def test_extract_notes_rejects_a_missing_version() -> None:
    with pytest.raises(release_notes.ReleaseNotesError, match=r"no section for 9\.9\.9"):
        release_notes.extract_notes(CHANGELOG, "9.9.9")


def test_extract_notes_rejects_an_empty_section() -> None:
    changelog = "## [1.0.1] - 2026-11-02\n\n\n## [1.0.0] - 2026-11-01\n\n- Old.\n"

    with pytest.raises(release_notes.ReleaseNotesError, match=r"section for 1\.0\.1 is empty"):
        release_notes.extract_notes(changelog, "1.0.1")


def test_main_writes_notes_for_the_given_version(tmp_path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    output = tmp_path / "out" / "RELEASE_NOTES.md"

    release_notes.main(["2.0.0", "--changelog", str(changelog), "--output", str(output)])

    assert output.read_text(encoding="utf-8") == "### Added\n\n- A feature.\n"


def test_main_defaults_to_the_canonical_version(tmp_path, monkeypatch, capsys) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(release_notes, "get_canonical_version", lambda: "2.0.1")

    release_notes.main(["--changelog", str(changelog)])

    assert capsys.readouterr().out.startswith("This patch fixes two bugs.")


def test_main_exits_1_with_a_message_when_the_section_is_missing(tmp_path, capsys) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        release_notes.main(["9.9.9", "--changelog", str(changelog)])

    assert excinfo.value.code == 1
    assert "no section for 9.9.9" in capsys.readouterr().err


def test_main_exits_1_when_the_changelog_cannot_be_read(tmp_path, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        release_notes.main(["1.0.0", "--changelog", str(tmp_path / "missing.md")])

    assert excinfo.value.code == 1
    assert "could not read" in capsys.readouterr().err


def test_repository_changelog_has_notes_for_the_current_version() -> None:
    changelog = (release_notes.ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert release_notes.extract_notes(changelog, release_notes.get_canonical_version()).strip()
