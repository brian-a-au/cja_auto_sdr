"""Equivalence tests for vectorized markdown cell escaping in the SDR markdown writer.

Confirms the vectorized `df.where(...).astype(str)` + chained `.str.replace(...)` escaping
used in `df_to_markdown_table` (src/cja_auto_sdr/output/sdr/__init__.py) produces byte-identical
output to the original per-cell `escape_markdown()` reference implementation.
"""

import numpy as np
import pandas as pd


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
        }
    )
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
