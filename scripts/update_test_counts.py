"""
Update test-count references in documentation using pytest collection output.

Usage:
  uv run python scripts/update_test_counts.py           # update files in-place
  uv run python scripts/update_test_counts.py --check   # fail if updates are needed

The script also validates that every collected ``tests/test_*.py`` module is
represented in the tests/README inventory tree and count table.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Keep the repo root importable when the script is launched via its file path.
    sys.path.insert(0, str(ROOT))

from tests.category_rules import ALL_TEST_MARKERS, PRIMARY_TEST_MARKERS, auto_test_markers_for_file  # noqa: E402

GENERATED_CATEGORY_BLOCK_START = "<!-- BEGIN GENERATED TEST CATEGORY SUMMARY -->"
GENERATED_CATEGORY_BLOCK_END = "<!-- END GENERATED TEST CATEGORY SUMMARY -->"


@dataclass(frozen=True)
class CategoryStats:
    tests: int = 0
    files: int = 0


def run_pytest_collect() -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("pytest collection failed. stderr:\n" + (proc.stderr.strip() or "(empty)"))
    return proc.stdout


def parse_counts(collect_output: str) -> dict[str, int]:
    module_re = re.compile(r"^\s*<Module ([^>]+)>")
    func_re = re.compile(r"^\s*<Function ")
    counts: dict[str, int] = {}
    current: str | None = None
    for line in collect_output.splitlines():
        mod_match = module_re.match(line)
        if mod_match:
            module_path = mod_match.group(1).strip()
            module_name = Path(module_path).name
            if module_name.startswith("test_"):
                current = module_name
                counts.setdefault(current, 0)
            else:
                current = None
            continue
        if current and func_re.match(line):
            counts[current] += 1
    return counts


def summarize_test_categories(counts: dict[str, int]) -> dict[str, dict[str, CategoryStats]]:
    marker_counts = {marker: CategoryStats() for marker in ALL_TEST_MARKERS}
    primary_counts = {marker: CategoryStats() for marker in PRIMARY_TEST_MARKERS}
    ci_slice_counts = {
        "test-unit": CategoryStats(),
        "test-integration": CategoryStats(),
        "smoke-test": CategoryStats(),
    }

    for module_name, test_count in counts.items():
        markers = set(auto_test_markers_for_file(module_name))

        for marker in ALL_TEST_MARKERS:
            if marker in markers:
                current = marker_counts[marker]
                marker_counts[marker] = CategoryStats(
                    tests=current.tests + test_count,
                    files=current.files + 1,
                )

        for marker in PRIMARY_TEST_MARKERS:
            if marker in markers:
                current = primary_counts[marker]
                primary_counts[marker] = CategoryStats(
                    tests=current.tests + test_count,
                    files=current.files + 1,
                )
                break

        if "unit" in markers and "slow" not in markers:
            current = ci_slice_counts["test-unit"]
            ci_slice_counts["test-unit"] = CategoryStats(
                tests=current.tests + test_count,
                files=current.files + 1,
            )

        if {"integration", "e2e", "slow"} & markers:
            current = ci_slice_counts["test-integration"]
            ci_slice_counts["test-integration"] = CategoryStats(
                tests=current.tests + test_count,
                files=current.files + 1,
            )

        if "smoke" in markers:
            current = ci_slice_counts["smoke-test"]
            ci_slice_counts["smoke-test"] = CategoryStats(
                tests=current.tests + test_count,
                files=current.files + 1,
            )

    return {
        "primary": primary_counts,
        "markers": marker_counts,
        "ci_slices": ci_slice_counts,
    }


def documented_test_files_in_tests_readme(text: str) -> dict[str, set[str]]:
    tree_files: set[str] = set()
    table_files: set[str] = set()

    for line in text.splitlines():
        tree_match = re.match(r"^\s*(?:├──|└──)\s+(test_[^\s]+)", line)
        if tree_match:
            tree_files.add(tree_match.group(1))

        table_match = re.match(r"^\|\s+`(test_[^`]+)`\s+\|", line)
        if table_match:
            table_files.add(table_match.group(1))

    return {"tree": tree_files, "table": table_files}


def find_tests_readme_inventory_mismatches(
    text: str,
    counts: Mapping[str, int],
) -> dict[str, tuple[str, ...]]:
    documented = documented_test_files_in_tests_readme(text)
    collected = set(counts)

    return {
        "missing_tree_entries": tuple(sorted(collected - documented["tree"])),
        "missing_count_rows": tuple(sorted(collected - documented["table"])),
        "stale_tree_entries": tuple(sorted(documented["tree"] - collected)),
        "stale_count_rows": tuple(sorted(documented["table"] - collected)),
    }


def render_category_summary_markdown(
    summary: dict[str, dict[str, CategoryStats]],
    total: int,
    *,
    heading_level: str | None = "###",
    heading_title: str = "Test Category Breakdown",
) -> str:
    lines: list[str] = []
    if heading_level:
        lines.extend([f"{heading_level} {heading_title}", ""])

    lines.extend(
        [
            "| Category | Tests | Files | Notes |",
            "|----------|-------|-------|-------|",
            (
                "| `unit` | "
                f"{summary['primary']['unit'].tests:,} | {summary['primary']['unit'].files} | "
                "Default primary category for files without explicit integration/e2e/smoke scope |"
            ),
            (
                "| `integration` | "
                f"{summary['primary']['integration'].tests:,} | {summary['primary']['integration'].files} | "
                "Cross-module integration suites |"
            ),
            (
                "| `e2e` | "
                f"{summary['primary']['e2e'].tests:,} | {summary['primary']['e2e'].files} | "
                "End-to-end suites with a mocked external boundary |"
            ),
            (
                "| `smoke` | "
                f"{summary['primary']['smoke'].tests:,} | {summary['primary']['smoke'].files} | "
                "Lightweight command-mode coverage |"
            ),
            (
                "| `slow` | "
                f"{summary['markers']['slow'].tests:,} | {summary['markers']['slow'].files} | "
                "Overlay marker; these tests are also counted in a primary category |"
            ),
            f"| **Primary Total** | **{total:,}** | **{sum(stats.files for stats in summary['primary'].values())}** | **unit + integration + e2e + smoke** |",
            "",
            "| CI Slice | Tests | Files | Selector |",
            "|----------|-------|-------|----------|",
            (
                "| `test-unit` | "
                f"{summary['ci_slices']['test-unit'].tests:,} | {summary['ci_slices']['test-unit'].files} | "
                '`-m "unit and not slow"` |'
            ),
            (
                "| `test-integration` | "
                f"{summary['ci_slices']['test-integration'].tests:,} | {summary['ci_slices']['test-integration'].files} | "
                '`-m "integration or e2e or slow"` |'
            ),
            (
                "| `smoke-test` | "
                f"{summary['ci_slices']['smoke-test'].tests:,} | {summary['ci_slices']['smoke-test'].files} | "
                "`-m smoke` |"
            ),
            "",
            "> Coverage note: the `--cov-fail-under=95` gate currently runs only in the `test-unit` CI slice.",
        ],
    )
    return "\n".join(lines) + "\n"


def replace_generated_block(text: str, replacement: str) -> str:
    pattern = re.compile(
        rf"{re.escape(GENERATED_CATEGORY_BLOCK_START)}\n.*?{re.escape(GENERATED_CATEGORY_BLOCK_END)}",
        re.DOTALL,
    )
    block = f"{GENERATED_CATEGORY_BLOCK_START}\n{replacement.rstrip()}\n{GENERATED_CATEGORY_BLOCK_END}"
    if pattern.search(text):
        return pattern.sub(block, text)
    return text.replace(
        "### Test Count Breakdown\n",
        f"### Test Count Breakdown\n\n{block}\n\n",
        1,
    )


def update_readme(text: str, total: int) -> str:
    return re.sub(
        r"Test suite \(.*?tests\)",
        f"Test suite ({total:,}+ tests)",
        text,
    )


def update_tests_readme(
    text: str,
    counts: dict[str, int],
    total: int,
    summary: dict[str, dict[str, CategoryStats]],
) -> str:
    lines = text.splitlines()
    updated: list[str] = []

    for original_line in lines:
        updated_line = original_line
        if updated_line.strip().startswith("**Total:") and "comprehensive tests" in updated_line:
            updated_line = f"**Total: {total:,} comprehensive tests**"

        if updated_line.strip().startswith("| **Total** |"):
            updated_line = f"| **Total** | **{total:,}** | **Collected via pytest --collect-only** |"

        # Update table rows for test files
        if updated_line.strip().startswith("| `test_") and "|" in updated_line:
            match = re.search(r"`(test_[^`]+)`", updated_line)
            if match:
                test_file = match.group(1)
                if test_file in counts:
                    updated_line = re.sub(
                        r"\| `test_[^`]+` \| \d+ \|",
                        f"| `{test_file}` | {counts[test_file]} |",
                        updated_line,
                    )

        # Update completed enhancements counts
        for test_file, count in counts.items():
            pattern = rf"({re.escape(test_file)}\) - )\d+ tests"
            if re.search(pattern, updated_line):
                updated_line = re.sub(pattern, rf"\g<1>{count} tests", updated_line)

        # Update overall total mentions
        if "Comprehensive test coverage" in updated_line:
            updated_line = re.sub(
                r"\(\d[\d,]* tests total\)",
                f"({total:,} tests total)",
                updated_line,
            )

        updated.append(updated_line)

    updated_text = "\n".join(updated) + "\n"
    category_summary = render_category_summary_markdown(
        summary,
        total,
        heading_level="####",
        heading_title="Category Summary",
    )
    return replace_generated_block(updated_text, category_summary)


def update_diff_comparison_docs(text: str, count: int) -> str:
    return re.sub(
        r"\*\*Total: \d+ tests\*\*",
        f"**Total: {count} tests**",
        text,
    )


def update_output_formats_docs(text: str, count: int) -> str:
    updated = re.sub(
        r"includes \d+ comprehensive tests covering",
        f"includes {count} comprehensive tests covering",
        text,
    )
    return re.sub(
        r"\*\*Fully Tested:\*\* \d+ comprehensive tests",
        f"**Fully Tested:** {count} comprehensive tests",
        updated,
    )


def apply_updates(files: list[tuple[Path, str]]) -> int:
    changed = 0
    for path, new_content in files:
        old_content = path.read_text()
        if old_content != new_content:
            path.write_text(new_content)
            changed += 1
    return changed


def write_summary_markdown(path: str, markdown: str) -> None:
    if path == "-":
        sys.stdout.write(markdown)
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(markdown)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if updates are needed.")
    parser.add_argument(
        "--write-summary-markdown",
        help="Append the generated test-category Markdown summary to this file path, or '-' for stdout.",
    )
    args = parser.parse_args()

    collect_output = run_pytest_collect()
    counts = parse_counts(collect_output)
    if not counts:
        raise RuntimeError("No tests detected from pytest collection output.")

    total = sum(counts.values())
    category_summary = summarize_test_categories(counts)

    files: list[tuple[Path, str]] = []

    readme_path = ROOT / "README.md"
    files.append((readme_path, update_readme(readme_path.read_text(), total)))

    tests_readme_path = ROOT / "tests" / "README.md"
    tests_readme_text = tests_readme_path.read_text()
    inventory_mismatches = find_tests_readme_inventory_mismatches(tests_readme_text, counts)
    files.append((tests_readme_path, update_tests_readme(tests_readme_text, counts, total, category_summary)))

    diff_docs_path = ROOT / "docs" / "DIFF_COMPARISON.md"
    if diff_docs_path.exists() and "test_diff_comparison.py" in counts:
        files.append(
            (diff_docs_path, update_diff_comparison_docs(diff_docs_path.read_text(), counts["test_diff_comparison.py"]))
        )

    output_docs_path = ROOT / "docs" / "OUTPUT_FORMATS.md"
    if output_docs_path.exists() and "test_output_formats.py" in counts:
        files.append(
            (
                output_docs_path,
                update_output_formats_docs(output_docs_path.read_text(), counts["test_output_formats.py"]),
            )
        )

    if args.write_summary_markdown:
        write_summary_markdown(args.write_summary_markdown, render_category_summary_markdown(category_summary, total))

    if any(inventory_mismatches.values()):
        for label, entries in inventory_mismatches.items():
            if entries:
                sys.stdout.write(f"tests/README.md {label}: {', '.join(entries)}\n")
        return 1

    if args.check:
        for path, new_content in files:
            if path.read_text() != new_content:
                sys.stdout.write(f"Out of date: {path.relative_to(ROOT)}\n")
                return 1
        sys.stdout.write("Test counts are up to date.\n")
        return 0

    changed = apply_updates(files)
    sys.stdout.write(f"Updated {changed} file(s).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
