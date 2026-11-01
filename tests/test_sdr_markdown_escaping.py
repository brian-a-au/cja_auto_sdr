"""Equivalence tests for vectorized markdown cell escaping in the SDR markdown writer.

Confirms the vectorized `df.astype(object).where(...).astype(str)` + chained
`.str.replace(...)` escaping used in `df_to_markdown_table`
(src/cja_auto_sdr/output/sdr/__init__.py) produces byte-identical output to the original
per-cell `escape_markdown()` reference implementation -- including for pandas nullable
extension dtypes (Int64, Float64, boolean, category) that the plain
`df.where(df.notna(), "").astype(str)` form cannot handle (it raises `TypeError` trying to
write the string "" into a typed extension array).
"""

import numpy as np
import pandas as pd

from cja_auto_sdr.output.sdr import df_to_markdown_table, escape_markdown


def _escape_markdown_ref(text):
    if pd.isna(text) or text is None:
        return ""
    text = str(text)
    text = text.replace("|", "\\|").replace("`", "\\`").replace("\n", " ").replace("\r", " ")
    return text.strip()


def test_vectorized_escaping_matches_reference():
    df = pd.DataFrame(
        {
            "a": ["plain", "has|pipe", "back`tick", "line\nbreak", "  spaced  "],
            "b": [1, 2.5, np.nan, None, "carriage\rreturn"],
            "c": [1.0, 2.5, np.nan, 100.0, 7.0],
        }
    )
    # Column "b" mixes in a string, so pandas infers object dtype at construction time
    # and never hits the numeric path. Column "c" must be genuinely float64 so that
    # `df.where(df.notna(), "")` exercises the numeric -> object upcast before `.astype(str)`.
    # Pin the dtype so construction-time inference can't silently regress this coverage.
    assert df["c"].dtype == "float64"
    ref_rows = [[_escape_markdown_ref(df.iloc[i][c]) for c in df.columns] for i in range(len(df))]

    df_esc = df.where(df.notna(), "").astype(str)
    for col in df_esc.columns:
        df_esc[col] = (
            df_esc[col]
            .str.replace("|", "\\|", regex=False)
            .str.replace("`", "\\`", regex=False)
            .str.replace("\n", " ", regex=False)
            .str.replace("\r", " ", regex=False)
            .str.strip()
        )
    new_rows = [list(t) for t in df_esc.itertuples(index=False)]
    assert new_rows == ref_rows


def _nullable_dtype_frame():
    """A frame covering the pandas nullable extension dtypes, each with a missing value."""
    return pd.DataFrame(
        {
            "int_col": pd.array([1, None, 3], dtype="Int64"),
            "float_col": pd.array([1.5, None, 3.5], dtype="Float64"),
            "bool_col": pd.array([True, None, False], dtype="boolean"),
            "cat_col": pd.Categorical(["x", None, "y|z"]),
        }
    )


def test_vectorized_escaping_matches_reference_for_nullable_extension_dtypes():
    """Int64 / Float64 / boolean / category columns with missing values must escape
    identically to the per-cell reference implementation.

    This is the exact equivalence check that the plain `df.where(df.notna(), "")` form
    fails on (TypeError writing "" into a typed extension array) -- reproduced directly
    against the production function below in
    `test_df_to_markdown_table_handles_nullable_extension_dtypes`.
    """
    df = _nullable_dtype_frame()
    assert str(df["int_col"].dtype) == "Int64"
    assert str(df["float_col"].dtype) == "Float64"
    assert str(df["bool_col"].dtype) == "boolean"
    assert str(df["cat_col"].dtype) == "category"

    ref_rows = [[_escape_markdown_ref(df.iloc[i][c]) for c in df.columns] for i in range(len(df))]

    df_obj = df.astype(object)
    df_esc = df_obj.where(df_obj.notna(), "").astype(str)
    for col in df_esc.columns:
        df_esc[col] = (
            df_esc[col]
            .str.replace("|", "\\|", regex=False)
            .str.replace("`", "\\`", regex=False)
            .str.replace("\n", " ", regex=False)
            .str.replace("\r", " ", regex=False)
            .str.strip()
        )
    new_rows = [list(t) for t in df_esc.itertuples(index=False)]
    assert new_rows == ref_rows


def test_df_to_markdown_table_handles_nullable_extension_dtypes():
    """Pins the actual production seam: `df_to_markdown_table` must render nullable
    extension dtype columns without raising, and the rendered table must match the
    table built from the per-cell reference escaper.
    """
    df = _nullable_dtype_frame()

    ref_rows = [[_escape_markdown_ref(df.iloc[i][c]) for c in df.columns] for i in range(len(df))]
    headers = [_escape_markdown_ref(col) for col in df.columns]
    expected = "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(row) + " |" for row in ref_rows],
        ]
    )

    result = df_to_markdown_table(df, "Nullable Types")
    assert result == expected


def test_escape_markdown_handles_list_values():
    """List-like cells must render as their escaped str() form, not raise.

    `pd.isna` returns an ndarray for list input, and truth-testing that array
    raises ValueError. Every sibling formatter guards this; escape_markdown
    must too.
    """
    assert escape_markdown(["a|b", "c"]) == "['a\\|b', 'c']"


def _gfm_cell_count(line):
    # GFM: a backslash escapes the next char; an unescaped pipe splits cells.
    import re

    return len(re.findall(r"(?:\\.|[^|\\])*\|", line)) - 1


def test_backslash_before_pipe_keeps_cell_count():
    df = pd.DataFrame([{"id": "metrics/a", "name": "Path C:\\|x", "description": "d"}])
    lines = df_to_markdown_table(df, "Metrics").split("\n")
    assert _gfm_cell_count(lines[0]) == 3
    assert _gfm_cell_count(lines[2]) == 3
    assert "Path C:\\\\\\|x" in lines[2]
    assert escape_markdown("Path C:\\|x") == "Path C:\\\\\\|x"


def _reference_df_to_markdown_table(df, sheet_name, empty_message=None):
    """Copy of the pandas-vectorized implementation, kept as the byte-identical reference."""
    if df.empty:
        if empty_message:
            return f"\n*{escape_markdown(empty_message)}*\n"
        return f"\n*No {sheet_name.lower()} found.*\n"
    headers = [escape_markdown(col) for col in df.columns]
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    df_obj = df.astype(object)
    df_esc = df_obj.where(df_obj.notna(), "").astype(str)
    for col in df_esc.columns:
        df_esc[col] = (
            df_esc[col]
            .str.replace("\\", "\\\\", regex=False)
            .str.replace("|", "\\|", regex=False)
            .str.replace("`", "\\`", regex=False)
            .str.replace("\n", " ", regex=False)
            .str.replace("\r", " ", regex=False)
            .str.strip()
        )
    data_rows = ["| " + " | ".join(row) + " |" for row in df_esc.itertuples(index=False)]
    return "\n".join([header_row, separator_row, *data_rows])


def test_markdown_table_matches_reference():
    frames = [
        pd.DataFrame(
            {
                "name": ["a|b", "back\\slash", "multi\nline\r\nx", "  padded  ", "tick`s", None, np.nan],
                "n": [1, 2, 3, 4, 5, 6, 7],
                "f": [1.5, np.nan, 3.0, 4.25, 5.0, 6.0, 7.0],
                "b": [True, False, True, False, True, False, True],
                "u": ["café", "日本語", "\U0001f600", "x", "y", "z", "w"],
            }
        ),
        pd.DataFrame(
            {
                "i": pd.array([1, None, 3], dtype="Int64"),
                "f": pd.array([1.5, None, 3.5], dtype="Float64"),
                "b": pd.array([True, None, False], dtype="boolean"),
                "c": pd.Categorical(["a|b", None, "c"]),
                "s": pd.array(["x", pd.NA, "y\nz"], dtype="string"),
                "o": [None, pd.NA, np.nan],
            }
        ),
        pd.DataFrame({"a": [1]}),
        pd.DataFrame({"p|ipe": ["v"], "back\\": ["w"]}),
        pd.DataFrame(),
        pd.DataFrame({"a": []}),
    ]
    for df in frames:
        assert df_to_markdown_table(df, "Sheet", "empty|msg") == _reference_df_to_markdown_table(
            df, "Sheet", "empty|msg"
        )
        assert df_to_markdown_table(df, "Sheet") == _reference_df_to_markdown_table(df, "Sheet")
