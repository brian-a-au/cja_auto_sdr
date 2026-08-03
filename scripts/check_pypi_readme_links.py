"""Reject repository-relative links in PyPI long descriptions.

PyPI renders the distribution metadata without a repository base URL, so links
such as ``docs/INSTALLATION.md`` point back into pypi.org instead of GitHub.

Usage:
  uv run python scripts/check_pypi_readme_links.py dist/*
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+).*?\1")
MARKDOWN_DESTINATION = re.compile(r"]\(\s*(?:<([^>\n]+)>|([^\s)]+))")
REFERENCE_DESTINATION = re.compile(r" {0,3}\[[^]]+]:\s*(?:<([^>\n]+)>|([^\s]+))")


@dataclass(frozen=True)
class LinkIssue:
    """One unsupported link in a rendered long description."""

    line: int
    target: str


class _HTMLDestinationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.issues: list[LinkIssue] = []

    def _record_attributes(self, attrs: list[tuple[str, str | None]]) -> None:
        line, _ = self.getpos()
        for name, value in attrs:
            if name.lower() in {"href", "src"} and value and _is_unsupported_relative_target(value):
                self.issues.append(LinkIssue(line=line, target=value))

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_attributes(attrs)

    def handle_startendtag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_attributes(attrs)


def _is_unsupported_relative_target(target: str) -> bool:
    return not (target.startswith(("#", "//")) or urlsplit(target).scheme)


def _prose_lines(markdown: str) -> list[tuple[int, str]]:
    """Return lines outside fenced code blocks with inline code removed."""
    prose: list[tuple[int, str]] = []
    fence_char = ""
    fence_length = 0

    for line_number, line in enumerate(markdown.splitlines(), start=1):
        match = FENCE.match(line)
        if fence_char:
            if match and match.group(1)[0] == fence_char and len(match.group(1)) >= fence_length:
                fence_char = ""
                fence_length = 0
            prose.append((line_number, ""))
            continue

        if match:
            marker = match.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            prose.append((line_number, ""))
            continue

        prose.append((line_number, INLINE_CODE.sub("", line)))

    return prose


def find_unsupported_relative_links(markdown: str) -> list[LinkIssue]:
    """Return repository-relative Markdown and HTML destinations."""
    issues: list[LinkIssue] = []
    prose = _prose_lines(markdown)
    for line_number, line in prose:
        for pattern in (MARKDOWN_DESTINATION, REFERENCE_DESTINATION):
            for match in pattern.finditer(line):
                target = match.group(1) or match.group(2)
                if _is_unsupported_relative_target(target):
                    issues.append(LinkIssue(line=line_number, target=target))

    html_parser = _HTMLDestinationParser()
    html_parser.feed("\n".join(line for _, line in prose))
    issues.extend(html_parser.issues)
    return issues


def _metadata_payload(data: bytes, *, source: Path) -> str:
    message = BytesParser(policy=policy.default).parsebytes(data)
    payload = message.get_payload()
    if not isinstance(payload, str):
        raise ValueError(f"{source}: metadata long description is not text")
    return payload


def read_long_description(path: Path) -> str:
    """Read a README or the long description embedded in a wheel/sdist."""
    if path.suffix.lower() in {".md", ".markdown"}:
        return path.read_text(encoding="utf-8")

    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            candidates = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(candidates) != 1:
                raise ValueError(f"{path}: expected one wheel METADATA file, found {len(candidates)}")
            return _metadata_payload(archive.read(candidates[0]), source=path)

    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, mode="r:gz") as archive:
            candidates = [
                member
                for member in archive.getmembers()
                if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO")
            ]
            if len(candidates) != 1:
                raise ValueError(f"{path}: expected one sdist PKG-INFO file, found {len(candidates)}")
            extracted = archive.extractfile(candidates[0])
            if extracted is None:
                raise ValueError(f"{path}: could not read sdist PKG-INFO")
            return _metadata_payload(extracted.read(), source=path)

    raise ValueError(f"{path}: expected a Markdown file, wheel, or .tar.gz sdist")


def check_paths(paths: list[Path]) -> list[str]:
    """Return validation errors for all supplied artifacts."""
    errors: list[str] = []
    for path in paths:
        try:
            description = read_long_description(path)
        except (OSError, UnicodeDecodeError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
            errors.append(str(exc))
            continue

        errors.extend(
            f"{path}:{issue.line}: unsupported relative PyPI README link: {issue.target}"
            for issue in find_unsupported_relative_links(description)
        )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate PyPI README links in built distributions.")
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown, wheel, or sdist paths to validate")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    errors = check_paths(args.paths)
    if errors:
        sys.stdout.write("PyPI README link check FAILED\n\n")
        sys.stdout.write("\n".join(f"  {error}" for error in errors) + "\n")
        raise SystemExit(1)

    sys.stdout.write(f"PyPI README link check OK: {len(args.paths)} artifact(s) validated\n")


if __name__ == "__main__":
    main()
