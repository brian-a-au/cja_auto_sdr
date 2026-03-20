from scripts.update_test_counts import (
    GENERATED_CATEGORY_BLOCK_END,
    GENERATED_CATEGORY_BLOCK_START,
    parse_counts,
    render_category_summary_markdown,
    summarize_test_categories,
    update_tests_readme,
)


def test_parse_counts_with_paths():
    output = """
<Module tests/test_alpha.py>
  <Function test_one>
  <Function test_two>
<Module tests/unit/test_beta.py>
  <Function test_three>
<Module scripts/helper.py>
  <Function helper_func>
""".strip()
    counts = parse_counts(output)
    assert counts == {
        "test_alpha.py": 2,
        "test_beta.py": 1,
    }


def test_parse_counts_without_paths():
    output = """
<Module test_gamma.py>
  <Function test_a>
  <Function test_b>
""".strip()
    counts = parse_counts(output)
    assert counts == {"test_gamma.py": 2}


def test_summarize_test_categories_rolls_up_primary_markers_and_ci_slices():
    counts = {
        "test_alpha.py": 3,
        "test_git_integration.py": 5,
        "test_cli_color_policy_e2e.py": 7,
        "test_cli_smoke_modes.py": 11,
        "test_perf.py": 13,
    }

    summary = summarize_test_categories(counts)

    assert summary["primary"]["unit"].tests == 16
    assert summary["primary"]["integration"].tests == 5
    assert summary["primary"]["e2e"].tests == 7
    assert summary["primary"]["smoke"].tests == 11
    assert summary["markers"]["slow"].tests == 13
    assert summary["ci_slices"]["test-unit"].tests == 3
    assert summary["ci_slices"]["test-integration"].tests == 25
    assert summary["ci_slices"]["smoke-test"].tests == 11


def test_render_category_summary_markdown_includes_ci_selectors():
    summary = summarize_test_categories({"test_alpha.py": 3, "test_perf.py": 2})

    markdown = render_category_summary_markdown(summary, total=5)

    assert "### Test Category Breakdown" in markdown
    assert '`-m "unit and not slow"`' in markdown
    assert '`-m "integration or e2e or slow"`' in markdown
    assert "| `slow` | 2 | 1 |" in markdown


def test_update_tests_readme_replaces_generated_category_block():
    original = f"""
# Test README

### Test Count Breakdown

{GENERATED_CATEGORY_BLOCK_START}
old content
{GENERATED_CATEGORY_BLOCK_END}
""".lstrip()

    counts = {"test_alpha.py": 2}
    total = 2
    summary = summarize_test_categories(counts)

    updated = update_tests_readme(original, counts, total, summary)

    assert "old content" not in updated
    assert GENERATED_CATEGORY_BLOCK_START in updated
    assert GENERATED_CATEGORY_BLOCK_END in updated
    assert "| `unit` | 2 | 1 |" in updated
