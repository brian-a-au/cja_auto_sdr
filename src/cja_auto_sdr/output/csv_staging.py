"""Publish an SDR CSV bundle as a staged set of files with a completion manifest."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd

from cja_auto_sdr.core.exceptions import OutputError

CSV_MANIFEST_NAME: Final = "_manifest.json"
CSV_MANIFEST_VERSION: Final = "1.0"


def csv_member_name(sheet_name: str) -> str:
    """Return the CSV file name for a sheet, rejecting names that could escape the bundle."""
    name = sheet_name.replace(" ", "_").lower() + ".csv"
    if "/" in name or "\\" in name or ".." in name:
        raise OutputError(f"Unsafe CSV file name for section {sheet_name!r}: {name!r}")
    return name


def publish_csv_bundle(frames: Mapping[str, pd.DataFrame], csv_dir: str | Path) -> Path:
    """Write every frame to a staging directory, then publish members and the manifest.

    The manifest is written last, so a consumer that finds ``_manifest.json`` knows the
    members it lists were all published. Replacing several files is not atomic: a failure
    while publishing leaves no manifest. Files that are not in the new member list are
    never deleted.
    """
    if not frames:
        raise OutputError("No CSV sections to write")

    members: dict[str, tuple[str, pd.DataFrame]] = {}
    for sheet_name, frame in frames.items():
        member = csv_member_name(sheet_name)
        if member in members:
            raise OutputError(f"CSV sections {members[member][0]!r} and {sheet_name!r} both map to {member}")
        members[member] = (sheet_name, frame)

    target = Path(csv_dir)
    target.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".csv-", dir=target))
    try:
        entries: list[dict[str, str | int]] = []
        for member, (sheet_name, frame) in members.items():
            staged = staging_dir / member
            frame.to_csv(staged, index=False, encoding="utf-8")
            data = staged.read_bytes()
            entries.append(
                {
                    "name": member,
                    "sheet": sheet_name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "rows": len(frame),
                    "bytes": len(data),
                },
            )
        manifest = {
            "manifest_version": CSV_MANIFEST_VERSION,
            "complete": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "files": entries,
        }
        staged_manifest = staging_dir / CSV_MANIFEST_NAME
        staged_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        (target / CSV_MANIFEST_NAME).unlink(missing_ok=True)
        for member in members:
            os.replace(staging_dir / member, target / member)
        os.replace(staged_manifest, target / CSV_MANIFEST_NAME)
    finally:
        with suppress(Exception):
            shutil.rmtree(staging_dir, ignore_errors=True)
    return target
