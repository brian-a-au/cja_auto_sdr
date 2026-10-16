# Representative offline workload baselines

`scripts/benchmark_workloads.py` records repeated latency samples, separate
Python allocation peaks, and deterministic correctness digests for the checked
out revision. It changes no production code. Synthetic API payloads exercise
real processing, quality validation, transformation, and output writers without
credentials or Adobe API calls. Fixture construction is versioned with the
harness; compare runs using the same harness, configuration, interpreter,
dependencies, and hardware.

## Reproduction

From the repository root, using the existing environment with the clustering
extra installed:

```bash
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --output /tmp/cja-workloads-before.json
# Check out the candidate revision, retaining the same harness and environment.
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --output /tmp/cja-workloads-after.json
```

Use an otherwise idle machine and run revisions serially. Defaults are seven
samples, two warmups, 1,000 components per data view, 25 organization views,
and four batch workers processed sequentially. Components must be an even
number of at least four; view count must be at least two. Scenario selection
keeps expensive or irrelevant paths out of focused comparisons:

```bash
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios cli-version cli-help cli-exit-codes --samples 15
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios sdr-json sdr-excel --components 10000
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios org-similarity org-clustering --views 50 --components 2000
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios batch-workers cache-miss cache-hit
```

The harness requires `PYTHONHASHSEED=0`. The optional clustering dependency is
required when selecting `org-clustering`; missing scipy fails rather than
silently measuring a skipped workload. Output includes Python/platform,
installed core dependency versions, revision, dirty-tree status, lockfile hash,
fixture parameters, raw samples, medians, and correctness SHA-256 digests.
Write results outside the repository so benchmark artifacts do not change its
dirty status. A nonzero exit or a changed digest requires investigation before
interpreting a latency improvement.

## Scenarios and boundaries

| Scenario | Production path and fixture |
|---|---|
| `cli-version`, `cli-help`, `cli-exit-codes` | Fresh `python -m cja_auto_sdr` invocation for the corresponding flag; stdout digest |
| `sdr-json`, `sdr-excel` | `process_single_dataview`; fixture API initializer/fetch boundary; real validation and report generation, including temporary filesystem writes |
| `org-similarity` | Component index, distribution, and similarity matrix; half shared/half view-specific metric and dimension IDs; overlap threshold 0.1 |
| `org-clustering` | Same analysis, with shared precomputed Jaccard distances passed to similarity and real scipy hierarchical clustering |
| `batch-workers` | Production `process_single_dataview_worker` entry point for each fixture view, sequentially; JSON output for each worker |
| `cache-miss`, `cache-hit` | Real `DataQualityChecker.check_all_quality_issues_optimized` with `ValidationCache` on metrics; clear before each miss, retain populated cache for hits |

SDR and validation fixtures contain equal numbers of metrics and dimensions,
missing descriptions every 31 rows, repeated-name opportunities every 97 rows,
and markup/non-ASCII description text. Inputs and outputs live in isolated
temporary directories. The API initializer and fetcher are replaced at their
boundary, following the existing offline integration-test pattern. Socket
connections are denied in workload workers as a backstop against accidental
network use. Logging is suppressed so console throughput does not dominate.

Every non-CLI sample uses two fresh subprocesses. `cold_process_seconds`
measures one complete worker launch with no warmups: interpreter/imports,
fixture setup, one operation, artifact verification, and digest generation.
This is an offline harness cold-start measurement, including harness overhead;
it is not live CLI SDR or org-report latency. CLI scenarios directly measure
CLI process wall time. `warm_operation_seconds` measures one operation after
configured warmups in another fresh subprocess; imports and fixture preparation
are excluded. No timer instrumentation or tracemalloc runs during latency
samples. Garbage collection retains the interpreter's normal behavior.

A separate fresh subprocess warms the operation and measures
`peak_traced_bytes` with tracemalloc. This is the Python allocation peak during
one operation, not RSS, a subprocess-tree peak, or native-library allocation
usage. CLI scenarios intentionally leave this field null. Cold organization
measurements include scipy imports when clustering is selected; warm
measurements exclude import costs.

After timing, the harness checks successful SDR results, component counts,
and XLSX structure. It hashes parsed JSON and semantic workbook content. Workbook shared strings
are resolved into cell values, cell styles and worksheet settings are retained,
and XML members are sorted by name; ZIP container metadata is excluded. Generated timestamp
strings are normalized to `<timestamp>`; all other content is retained. It
hashes organization models after dataclass conversion and sorted sets. Quality issue rows in JSON and Excel, and cache issues, are sorted to avoid
validation thread completion ordering. Every cold,
warm, and allocation sample must have exactly the same digest. These digests
are regression signals, not independent semantic oracles; existing tests
remain the authority for intended behavior. Compare digests between revisions
as well as within a run.

## Limits and validation

This harness does not claim live API throughput, real organization shape,
process-pool spawn/IPC throughput, shared multiprocessing-cache performance,
org report locking/disk-cache latency, or full org-report CLI latency. The
batch scenario isolates worker processing costs; it deliberately avoids
substituting a thread executor and calling the result multiprocessing latency.
The cache scenario covers local validation hashing, hit copying, and miss
validation. Those boundaries make measurements reproducible offline without
changing production paths or adding production instrumentation.

Smoke all scenarios with a small fixture before collecting baseline numbers:

```bash
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --samples 2 --warmups 1 --components 20 --views 3 --batch-size 2 --output /tmp/cja-workloads-smoke.json
.venv/bin/ruff check scripts/benchmark_workloads.py
.venv/bin/ruff format --check scripts/benchmark_workloads.py
```

Tiny smoke measurements validate execution and deterministic output only;
they are not representative performance results. No absolute machine-specific
latency gate or speedup claim is introduced by this baseline harness.

## Baseline measurements

Measured on macOS 26.6.2 arm64, CPython 3.14.0, against production revision
`238b048`. The raw [baseline report](results/workloads-baseline.json) contains
all seven samples and dependency versions. The dirty flag reflects the new
harness and its tests; production code was unchanged. Excel was remeasured
after strengthening the semantic digest. Cold values include the harness
overhead described above. These are synthetic workloads, not live API timings.

| Scenario | Cold process median (ms) | Warm operation median (ms) | Peak Python allocation (MiB) |
|---|---:|---:|---:|
| cli-version | 92.59 | — | — |
| cli-help | 860.58 | — | — |
| cli-exit-codes | 98.73 | — | — |
| sdr-json | 949.65 | 15.98 | 0.485 |
| sdr-excel | 942.17 | 85.60 | 1.774 |
| org-similarity | 794.68 | 25.71 | 6.370 |
| org-clustering | 1119.67 | 27.70 | 6.386 |
| batch-workers | 868.01 | 59.62 | 0.562 |
| cache-miss | 599.56 | 1.82 | 0.086 |
| cache-hit | 567.81 | 0.78 | 0.086 |

Full baseline validation: 8,623 unit tests passed with three skips and 99.04%
coverage; 126 integration/end-to-end/slow tests passed. After review, the Excel
digest contract test and all 30 existing Excel formatting tests passed. The
digest test independently checks value types, row formatting and formulas,
and ignores shared-string index ordering and ZIP timestamps.
