"""Publish an SDR workbook only after every sheet and workbook close succeeds."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import pandas as pd

from cja_auto_sdr.core.exceptions import OutputError


@contextmanager
def staged_excel_writer(destination: str | Path) -> Iterator[pd.ExcelWriter]:
    """Stage beside the resolved target, retaining symlinks and ordinary file modes.

    Hardlinked and non-regular destinations cannot preserve their inode semantics
    with replacement, so reject them before rendering. New workbooks are created
    normally inside a short sibling directory, allowing the OS to apply umask.
    """
    target = Path(destination).resolve()
    try:
        previous = target.stat()
    except FileNotFoundError:
        previous = None
    if previous is not None:
        if not stat.S_ISREG(previous.st_mode):
            raise OutputError(f"Excel destination is not a regular file: {destination}. Choose a regular file path.")
        if previous.st_nlink > 1:
            raise OutputError(
                f"Excel destination has multiple hard links: {destination}. Choose an unlinked file path."
            )

    staging_dir = Path(tempfile.mkdtemp(prefix=".xlsx-", dir=target.parent))
    staged = staging_dir / "workbook.xlsx"
    try:
        workbook_file = staged.open("wb")
        try:
            writer = pd.ExcelWriter(workbook_file, engine="xlsxwriter")
            try:
                yield writer
            except BaseException:
                with suppress(Exception):
                    writer.close()
                raise
            else:
                writer.close()
        except BaseException:
            with suppress(Exception):
                workbook_file.close()
            raise
        else:
            workbook_file.close()
        if previous is not None:
            staged.chmod(stat.S_IMODE(previous.st_mode))
        os.replace(staged, target)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
