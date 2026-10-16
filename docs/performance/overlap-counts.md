# Reuse streaming overlap counts

Similarity-only analysis previously intersected component sets once for every
pair, then again for each pair that passed the overlap threshold. The iterator
now carries the intersection and union counts to the retained pair. Rejected
pairs are still streamed; the dictionary-based private precomputation contract
is preserved. Threshold comparisons use unrounded scores and sorting retains
input order for rounded ties. Drift and name output are unchanged.

## Measurements

Same environment and fixture as the [workload baseline](workloads.md): seven
samples, 25 views, 1,000 components per view, overlap threshold 0.1. These
measurements include component-index construction and distribution. Imports,
fixture construction and digest calculation are outside the warm timer.

| Warm operation | Before (ms) | After (ms) | Reduction |
|---|---:|---:|---:|
| Similarity analysis | 25.707 | 19.993 | 22.2% |
| Similarity plus clustering | 27.700 | 29.079 | 5.0% longer in this run |

Correctness digests match exactly in both scenarios. Raw candidate samples are
in [overlap-counts.json](results/overlap-counts.json); baseline samples are in
[workloads-baseline.json](results/workloads-baseline.json). Timing observations
are synthetic, machine-specific results, not API latency claims. The explicit
precomputed dictionary path still calculates counts for accepted pairs; compact
clustering storage is a separate follow-up.

```bash
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios org-similarity org-clustering --output /tmp/overlap-counts.json
.venv/bin/pytest tests/test_org_analyzer_similarity.py tests/test_org_analyzer_coverage.py tests/test_exception_contracts.py -q --no-cov
```

The strengthened existing regression test observed 1,560 intersections for
780 accepted pairs before the change and 780 afterward. It also verifies that
all-rejected pairs remain streamed and validates retained counts. All 221
focused tests pass, including raw-threshold, stable-tie, drift, name, governance
and optional-clustering behavior.

Full verification on the final production change: 8,624 unit tests passed,
three skipped, 99.04% coverage; 126 integration/end-to-end/slow tests passed.

A same-process cross-check loaded the four original Jaccard/similarity methods
from trusted local revision `191ba5f` into a subclass and alternated before/after
order across 21 samples after three warmups. It used identical fixtures,
interpreter, imports and live dependencies, kept GC enabled, and asserted full
result equality before timing. Index/distribution construction stayed inside
the timer. This separated host drift from the small precomputed-path overhead:
similarity medians were 26.981 / 19.396 ms (28.1% reduction), while clustering
was 29.328 / 29.004 ms (no useful difference). [Paired samples](results/overlap-counts-paired.json)
are retained alongside the fresh-process runs. No clustering speedup is claimed.
