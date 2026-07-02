"""Characterization tests for `cja_auto_sdr.org.writers.csv.write_org_report_csv`.

Covers the distribution-bucket assignment for the components CSV, guarding the
refactor from an O(n) membership-list scan per component to an O(1) dict lookup
built once ahead of the loop (see B1 in the v3.11.2 performance plan).
"""

from __future__ import annotations

import logging
from pathlib import Path

from cja_auto_sdr.org.writers.csv import write_org_report_csv

# Exact `org_report_components.csv` body captured from a baseline run of the
# unchanged writer against `rich_org_report_result()`. Any refactor of the
# bucket-assignment logic must reproduce this byte-for-byte.
EXPECTED_COMPONENTS_CSV = (
    "Component ID,Component Type,Name,Data View Count,Coverage (%),Distribution Bucket,Data Views\n"
    "metric/common/1,Metric,Common Metric,2,100.0,Common,dv_001;dv_002\n"
    "dimension/common/1,Dimension,Common Dimension,2,100.0,Common,dv_001;dv_002\n"
    "metric/core/1,Metric,Core Metric One,2,100.0,Core,dv_001;dv_003\n"
    "metric/core/2,Metric,Core Metric Two,2,100.0,Core,dv_001;dv_003\n"
    "dimension/core/1,Dimension,Core Dimension,2,100.0,Core,dv_001;dv_003\n"
    "metric/isolated/1,Metric,Isolated Metric,1,50.0,Isolated,dv_003\n"
    "dimension/isolated/1,Dimension,Isolated Dimension,1,50.0,Isolated,dv_003\n"
    "metric/limited/1,Metric,Limited Metric,2,100.0,Limited,dv_001;dv_002\n"
    "dimension/limited/1,Dimension,Limited Dimension,2,100.0,Limited,dv_001;dv_002\n"
)


def test_components_csv_bucket_assignment_unchanged(tmp_path, rich_org_report_result):
    """Distribution-bucket assignment in the components CSV is byte-identical.

    Guards against regressions when the per-component `if/elif` membership-list
    scan is replaced with a single `bucket_by_id` dict built once before the
    loop.
    """
    result = rich_org_report_result
    logger = logging.getLogger("test_org_writers_csv")

    returned = write_org_report_csv(result, None, str(tmp_path), logger)

    body = (Path(returned) / "org_report_components.csv").read_text(encoding="utf-8")

    assert body == EXPECTED_COMPONENTS_CSV
