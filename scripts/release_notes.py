"""
Print the CHANGELOG.md section for one version, for use as release notes.

The release workflow uses this to fail when CHANGELOG.md has no section for
the version it is about to publish, and to write the GitHub release body.

Usage:
  uv run --no-project python scripts/release_notes.py              # current version
  uv run --no-project python scripts/release_notes.py 3.13.10 --output dist/RELEASE_NOTES.md
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

try:
    from scripts.check_version_sync import ROOT, get_canonical_version
except ModuleNotFoundError:  # run as a file: scripts/ is on sys.path, the repo root is not
    from check_version_sync import ROOT, get_canonical_version  # type: ignore[no-redef]

HEADING = re.compile(r"^## ", re.MULTILINE)


class ReleaseNotesError(Exception):
    """CHANGELOG.md has no usable section for the requested version."""


def extract_notes(changelog: str, version: str) -> str:
    """Return the body of the ``## [version]`` section, without its heading."""
    start = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n", changelog, re.MULTILINE)
    if start is None:
        raise ReleaseNotesError(f"CHANGELOG.md has no section for {version} (expected a '## [{version}]' heading)")
    following = HEADING.search(changelog, start.end())
    body = changelog[start.end() : following.start() if following else len(changelog)].strip()
    if not body:
        raise ReleaseNotesError(f"CHANGELOG.md section for {version} is empty")
    return body + "\n"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print the CHANGELOG.md section for a version.")
    parser.add_argument("version", nargs="?", help="Version to look up. Default: the version in version.py.")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md", help="Path to CHANGELOG.md.")
    parser.add_argument("--output", type=Path, help="Write the notes to this file instead of stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    version = args.version or get_canonical_version()
    try:
        changelog = args.changelog.read_text(encoding="utf-8")
        notes = extract_notes(changelog, version)
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"FAIL: could not read {args.changelog}: {exc}\n")
        raise SystemExit(1) from exc
    except ReleaseNotesError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        raise SystemExit(1) from exc

    if args.output is None:
        sys.stdout.write(notes)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")
    sys.stdout.write(f"Wrote release notes for {version} to {args.output}\n")


if __name__ == "__main__":
    main()
