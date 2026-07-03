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

from cja_auto_sdr.output.sdr import df_to_markdown_table


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
