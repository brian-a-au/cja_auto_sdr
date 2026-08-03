from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts import check_pypi_readme_links

ROOT = Path(__file__).resolve().parents[1]


def _metadata(description: str) -> bytes:
    return (
        "Metadata-Version: 2.4\n"
        "Name: example\n"
        "Version: 1.0.0\n"
        "Description-Content-Type: text/markdown\n"
        "\n"
        f"{description}"
    ).encode()


def test_readme_has_no_pypi_unsafe_relative_links() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    issues = check_pypi_readme_links.find_unsupported_relative_links(readme)

    assert issues == []


def test_find_unsupported_relative_links_allows_urls_and_fragments() -> None:
    markdown = "[Docs](https://example.com/docs) [Email](mailto:help@example.com) [Local](#install)"

    issues = check_pypi_readme_links.find_unsupported_relative_links(markdown)

    assert issues == []


def test_find_unsupported_relative_links_reports_nested_image_and_outer_targets() -> None:
    markdown = "[![Build](https://img.example/badge.svg)](tests/)\n[Guide](docs/GUIDE.md)"

    issues = check_pypi_readme_links.find_unsupported_relative_links(markdown)

    assert issues == [
        check_pypi_readme_links.LinkIssue(line=1, target="tests/"),
        check_pypi_readme_links.LinkIssue(line=2, target="docs/GUIDE.md"),
    ]


def test_find_unsupported_relative_links_reports_reference_and_html_targets() -> None:
    markdown = (
        "[Guide][guide]\n"
        "[guide]: <docs/GUIDE WITH SPACES.md>\n"
        '<a href="docs/API.md">API</a>\n'
        '<img src="images/example.png" />\n'
    )

    issues = check_pypi_readme_links.find_unsupported_relative_links(markdown)

    assert issues == [
        check_pypi_readme_links.LinkIssue(line=2, target="docs/GUIDE WITH SPACES.md"),
        check_pypi_readme_links.LinkIssue(line=3, target="docs/API.md"),
        check_pypi_readme_links.LinkIssue(line=4, target="images/example.png"),
    ]


def test_find_unsupported_relative_links_ignores_code_contexts() -> None:
    markdown = "`[Inline](docs/INLINE.md)`\n```markdown\n[Block](docs/BLOCK.md)\n```\n"

    issues = check_pypi_readme_links.find_unsupported_relative_links(markdown)

    assert issues == []


def test_read_long_description_reads_wheel_metadata(tmp_path: Path) -> None:
    wheel = tmp_path / "example-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        archive.writestr("example-1.0.0.dist-info/METADATA", _metadata("[Docs](https://example.com)\n"))

    description = check_pypi_readme_links.read_long_description(wheel)

    assert description == "[Docs](https://example.com)\n"


def test_read_long_description_reads_sdist_metadata(tmp_path: Path) -> None:
    sdist = tmp_path / "example-1.0.0.tar.gz"
    metadata = _metadata("[Docs](https://example.com)\n")
    info = tarfile.TarInfo("example-1.0.0/PKG-INFO")
    info.size = len(metadata)
    with tarfile.open(sdist, mode="w:gz") as archive:
        archive.addfile(info, io.BytesIO(metadata))

    description = check_pypi_readme_links.read_long_description(sdist)

    assert description == "[Docs](https://example.com)\n"


def test_check_paths_reports_artifact_and_line(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Example\n\n[Guide](docs/GUIDE.md)\n", encoding="utf-8")

    errors = check_pypi_readme_links.check_paths([readme])

    assert errors == [f"{readme}:3: unsupported relative PyPI README link: docs/GUIDE.md"]


def test_check_paths_rejects_non_inline_links_in_built_metadata(tmp_path: Path) -> None:
    wheel = tmp_path / "example-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        archive.writestr(
            "example-1.0.0.dist-info/METADATA",
            _metadata("[Guide][guide]\n\n[guide]: docs/GUIDE.md\n"),
        )

    sdist = tmp_path / "example-1.0.0.tar.gz"
    metadata = _metadata('<a href="docs/API.md">API</a>\n')
    info = tarfile.TarInfo("example-1.0.0/PKG-INFO")
    info.size = len(metadata)
    with tarfile.open(sdist, mode="w:gz") as archive:
        archive.addfile(info, io.BytesIO(metadata))

    errors = check_pypi_readme_links.check_paths([wheel, sdist])

    assert errors == [
        f"{wheel}:3: unsupported relative PyPI README link: docs/GUIDE.md",
        f"{sdist}:1: unsupported relative PyPI README link: docs/API.md",
    ]


def test_main_exits_nonzero_for_unsupported_link(tmp_path: Path, monkeypatch, capsys) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("[Guide](docs/GUIDE.md)\n", encoding="utf-8")
    monkeypatch.setattr(check_pypi_readme_links.sys, "argv", ["check_pypi_readme_links.py", str(readme)])

    with pytest.raises(SystemExit) as excinfo:
        check_pypi_readme_links.main()

    assert excinfo.value.code == 1
    assert "PyPI README link check FAILED" in capsys.readouterr().out
