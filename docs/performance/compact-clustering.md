# Compact clustering distances

Clustering retained a dictionary of tuple keys and Python float scores while
also allocating SciPy's condensed distance array. The internal precomputation
now keeps two compact arrays: exact intersection counts and canonical double
precision distances. SciPy reads the distance buffer without a second copy.
Similarity output reconstructs raw scores from integer counts; cohesion still
uses the original distance-to-similarity round trip. This distinction preserves
threshold decisions and rounding at floating-point boundaries.

The private result remains a mapping for existing readers. Callers supplying a
legacy dictionary still work. Similarity-only analysis remains streaming, and
the optional SciPy fallback is unchanged.

## Measurements

The [offline workload harness](workloads.md) ran with Python 3.14.0 and SciPy
1.18.1 on macOS arm64. Each scaled run used five samples after one warmup,
500 views and 20 components per view. Index construction, distribution,
similarity and clustering are inside the warm timer. Fixture creation, imports
and correctness hashing are outside it. This deliberately exercises the kernel
above the CLI's default similarity-size guardrail.

| Scaled clustering | Before | After | Change |
|---|---:|---:|---:|
| Peak traced allocation | 62,669,368 bytes | 45,718,944 bytes | 27.0% lower |
| Warm median | 379.281 ms | 257.546 ms | 32.1% shorter |
| Cold process median | 2.485 s | 2.775 s | 11.7% longer |

The full-result digest matches exactly. No cold-process speedup is claimed;
these samples include process startup and verification, and timing varies with
host load. Traced allocation is Python-visible allocation, not total RSS or a
bound on SciPy native workspace.

[Before samples](results/compact-clustering-before.json) were captured with the
preceding overlap-count change in the working tree on revision `191ba5f`;
[after samples](results/compact-clustering-after.json) were captured with this
change in the working tree on `a1d33bc`. Both reports retain the dirty-tree flag.
The same lockfile and interpreter were used. Dependencies include SciPy 1.18.1,
which the harness's dependency list does not yet record.

The regular fixture (25 views, 1,000 components, seven samples, two warmups)
also retained both correctness digests. Clustering's warm median changed from
29.079 to 18.821 ms and peak allocation from 6,696,056 to 6,650,232 bytes.
Similarity-only was 17.542 ms versus 19.993 ms, with unchanged allocation and
no production changes to that path. Treat these timings as local synthetic
observations, not API or end-to-end throughput claims.
[Regular samples](results/compact-clustering-regular.json) and the
[preceding baseline](results/overlap-counts.json) retain all observations.

```bash
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios org-clustering --views 500 --components 20 --samples 5 --warmups 1 --output /tmp/compact-clustering.json
PYTHONHASHSEED=0 .venv/bin/python scripts/benchmark_workloads.py --scenarios org-similarity org-clustering --samples 7 --warmups 2 --output /tmp/compact-regular.json
.venv/bin/pytest tests/test_org_analyzer_similarity.py tests/test_org_analyzer_coverage.py tests/test_exception_contracts.py -q --no-cov
```

All 226 focused tests pass. Added coverage checks exact raw fractions, mapping
order and invalid keys, no repeated intersections, shared-buffer use, cohesion
rounding and input immutability across all seven supported SciPy linkage methods.

Final gates: 8,629 unit tests passed (three skipped), 99.04% coverage; 126
integration/end-to-end/slow tests and ten smoke tests passed. Repository lint,
formatting and documented test-count checks passed.
