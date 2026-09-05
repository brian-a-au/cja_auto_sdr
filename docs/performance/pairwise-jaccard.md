# Pairwise Jaccard component-set reuse

## Scope and safety

`OrgComponentAnalyzer._compute_pairwise_jaccard` evaluated `all_component_ids`
twice for every nonempty, successful data view: once to filter summaries and
again to prepare the pairwise loop. Each property access allocates the union of
metric and dimension IDs. The patch retains the first union in a local list.
For N valid views, this reduces union construction from 2N to N. Empty successful
views still require one union; failed views require none.

Other candidates inspected were repeated change-type scans in diff summaries
and repeated word splitting in cluster naming. Component-set reuse was selected
because it eliminates allocations proportional to component count with a small
change and no changes to the pairwise arithmetic or downstream rendering.

The valid-summary and pair-index insertion orders are unchanged. Overlapping
metric/dimension IDs remain deduplicated. Empty views are excluded, and every
non-None error (including an empty string) skips component access. Invalid
component operands still raise TypeError. No API, CLI, validation, exception
handler, dependency, or persistent cache changes. Inputs are not mutated;
subsequent calls recompute unions and observe updated inputs. Component fetching
finishes before this analysis runs. Concurrent external mutation during this
method is not a supported consistency guarantee; no shared cache is introduced.

## Reproduction

From the repository root, with the baseline commit available in local git history:

```bash
UV_CACHE_DIR=/tmp/cja-perf-uv-cache uv sync --dev --extra clustering
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_pairwise_jaccard.py --baseline-ref 1e5b198082a4e37127b5d974b8727f560c36cae4 --baseline-only > /tmp/cja-jaccard-before.json
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_pairwise_jaccard.py --baseline-ref 1e5b198082a4e37127b5d974b8727f560c36cae4 > /tmp/cja-jaccard-paired.json
```

The baseline-only run was completed before editing production code. The paired
run loads the original method from that trusted git revision and benchmarks it
alongside the checked-out method in the same process, using identical fixtures,
imports, interpreter, GC settings, and hash seed. It asserts exact result equality
before timing. Only pass trusted revisions: the harness executes the extracted
method. Imports, fixture generation, git I/O, and correctness assertions are
outside the timed region. GC remains enabled.

Each implementation gets five warmup batches and 31 measured batches per case.
Execution order alternates between implementations. Each batch repeats the
helper 2,000 / 1,000 / 20 / 2 / 2 times respectively for the cases below. JSON
includes every sample, median, quartiles, minimum, maximum, and environment.
Run without other CPU-intensive work.

Synthetic views contain equal numbers of metrics and dimensions, with half the
IDs shared and half view-specific. This models the in-memory computation used
by org-report similarity and clustering after component fetching, including
small views, component-heavy views, and a larger view count. These are synthetic
workloads, not measurements of a particular Adobe organization.

## Measurements

Measured on macOS 26.6.2 arm64, CPython 3.14.5 (Clang 22.1.3), fixed hash seed 0.
All times below are microseconds per helper call. Brackets show Q1–Q3 across
31 batch averages, not confidence intervals.

| Views × components/view | Pre-edit median | Paired original median [Q1–Q3] | Modified median [Q1–Q3] | Absolute reduction | Time reduction |
|---|---:|---:|---:|---:|---:|
| 0 × 0 | 0.160 | 0.160 [0.155–0.166] | 0.148 [0.145–0.153] | 0.012 | immaterial |
| 3 × 20 | 2.867 | 2.864 [2.820–2.884] | 2.141 [2.112–2.175] | 0.723 | 25.24% |
| 5 × 2,000 | 877.710 | 880.731 [871.221–886.525] | 656.423 [649.790–669.733] | 224.308 | 25.47% |
| 25 × 2,000 | 16,764.188 | 16,619.354 [16,490.000–16,759.916] | 15,544.604 [15,467.334–15,667.021] | 1,074.750 | 6.47% |
| 5 × 10,000 | 5,987.459 | 5,972.208 [5,912.125–6,087.542] | 4,554.458 [4,528.520–4,684.917] | 1,417.750 | 23.74% |

Nonempty cases have separated interquartile ranges. No measured small-input
regression; the empty-input difference is too small to claim a useful speedup.
A second independent paired run with the same settings measured 25.57%, 24.86%,
7.89%, and 22.94% reductions for the four nonempty cases, respectively.
The percentage benefit declines as pairwise intersections dominate at higher
view counts. No end-to-end latency or peak-memory improvement is claimed.
Results may differ with hardware, Python version, overlap, and component counts.

## Correctness and checks

Regression tests cover exact values and pair order, original summary identity,
empty/single/40-view inputs, failed and empty-error summaries, overlapping IDs,
input immutability, mutation between calls, invalid-operand failure behavior,
and one property evaluation per successful summary. Existing org tests cover
similarity, drift, clustering, governance, and serialization.

```bash
.venv/bin/pytest tests/test_org_analyzer_similarity.py tests/test_org_analyzer_coverage.py tests/test_exception_contracts.py -q
UV_CACHE_DIR=/tmp/cja-perf-uv-cache .venv/bin/pytest tests/ -q --tb=short -m 'unit and not slow' -n auto --cov=cja_auto_sdr --cov-report=term --cov-fail-under=95 --durations=10
UV_CACHE_DIR=/tmp/cja-perf-uv-cache .venv/bin/pytest tests/ -q --tb=short -m 'integration or e2e or slow' --durations=10
UV_CACHE_DIR=/tmp/cja-perf-uv-cache .venv/bin/pytest tests/test_quality_policy_and_run_summary.py -q -m run_summary_contract
UV_CACHE_DIR=/tmp/cja-perf-uv-cache .venv/bin/pytest tests/ -q --tb=short -m smoke
.venv/bin/ruff check src/ tests/ scripts/ examples/
.venv/bin/ruff format --check src/ tests/ scripts/ examples/
UV_CACHE_DIR=/tmp/cja-perf-uv-cache uv lock --check --offline
git diff --check
```

Results: 192 focused tests passed; 8,294 unit tests passed, 3 skipped, 99.07%
coverage (95% gate); 101 integration/e2e/slow tests passed. Lint, format, lockfile,
and whitespace checks passed. The separate run-summary and smoke gates passed
(52 and 10 tests). Loading the original method into the same focused test suite
also passed all 191 behavioral tests; only the new single-evaluation assertion
was excluded because it intentionally distinguishes the optimization.
Initial sandbox runs failed on uv cache access,
local multiprocessing sockets, and terminal subprocess checks; the full slices
passed with a writable uv cache and normal local process permissions. Linux and
Windows execution remains for CI; no live Adobe API calls were needed.
