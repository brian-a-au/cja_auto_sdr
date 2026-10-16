# CLI help startup

The lightweight module entry point already probes the real argparse parser.
Successful help previously fell through to the generator, importing pandas,
NumPy, cjapy and tqdm before the parser printed the same help again. Reuse the
captured successful help output and exit before those imports.

The real parser remains the authority for precedence, abbreviations, short
option clusters and errors. Active shell completion and run-summary requests
still use the full entry point. No parser schema or help text is duplicated.

## Measurements

The [workload harness](workloads.md) runs a fresh Python subprocess for each CLI
sample, requires a successful exit and compares stdout digests. The baseline
used seven samples; the candidate used nine on the same Python 3.14.0, macOS
arm64 environment and lockfile. CLI samples have no per-sample warmups; the
`--warmups 2` setting applies only to non-CLI scenarios.

| Cold command | Baseline median | Candidate median |
|---|---:|---:|
| `--help` | 860.582 ms | 69.366 ms |
| `--version` | 92.586 ms | 68.698 ms |
| `--exit-codes` | 98.731 ms | 68.120 ms |

Help startup is **91.9% shorter** in this run. All three correctness digests
match. The existing fast commands are controls for host variation; their
smaller timing differences are not attributed to this change. These are local
process measurements, not live API or SDR generation speedups.

[Candidate samples](results/help-startup.json) and
[baseline samples](results/workloads-baseline.json) retain the environment,
lockfile hash, raw timings and digests. The candidate report's revision is the
parent `191ba5f`, with the working-tree flag recording the uncommitted change.

```bash
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios cli-version cli-help cli-exit-codes --samples 9 --warmups 2 --output /tmp/help-startup.json
.venv/bin/pytest tests/test_main_entry_points.py tests/test_early_exit.py -q --no-cov
```

Two regression tests compare 16 argument-order/error cases with the full entry
point, retain completion fallback, and check in a fresh subprocess that plain
help imports none of the heavy modules. The import test fails before the change.
