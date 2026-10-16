# Performance arc decisions

This arc adds reproducible offline baselines, reuses streaming overlap counts,
compacts clustering distances and speeds up CLI help. The following candidates
remain unchanged because the observable contract or measured benefit did not
support an implementation in this arc.

## Demand-aware component fetching: deferred

`ProcessingExecutionPolicy.required_component_endpoints` describes which
failures must fail closed. It is not a complete dependency list for consumers.
`ParallelAPIFetcher.fetch_all_data` fetches metrics, dimensions and data-view
metadata and records endpoint status, diagnostics and progress for all three.

Omitting an endpoint based only on output section flags would change observable
behavior:

- Standard validation consumes both component frames. Derived inventory also
  consumes both, even when a primary section is omitted.
- Embedded metadata and `ProcessingResult` counts still report both kinds of
  components. Inventory-only JSON, HTML, Markdown and Notion retain metadata;
  inventory-only CSV still produces completion counts and endpoint diagnostics.
- Metrics-only and dimensions-only flags primarily affect Excel sections;
  the shared standard output data retains both frames.
- Data-view lookup validates the request and supplies report identity/naming.

The relevant contracts are covered in `test_processing_execution_policy.py`,
`test_process_single_dataview.py`, `test_parallel_api_fetcher.py` and
`test_fetch_edge_cases.py`. A future optimization needs an explicit contract
for omitted counts, status and validation, or a complete consumer dependency
model that preserves them. No endpoint-skipping performance claim is made.

## Bounded batch submission: deferred

A parent-only experiment exercised the production `BatchProcessor` with an
immediate fake executor returning completed futures. It measured argument
construction, submission bookkeeping, future collection and result handling;
it did not run worker processes, API calls or SDR writers. Seven samples per
size, with a separate traced-allocation run, gave:

| Jobs | Median parent time | Peak traced allocation |
|---:|---:|---:|
| 10 | 0.084 ms | 40,624 bytes |
| 100 | 0.570 ms | 392,208 bytes |
| 1,000 | 6.351 ms | 3,912,688 bytes |
| 10,000 | 91.556 ms | 39,501,968 bytes |

[Raw samples](results/batch-submission-baseline.json) include the initial cold
sample; medians are not adjusted. The environment was the workload baseline's
Python 3.14.0/macOS arm64 installation. The experiment ran on `191ba5f` with the
overlap-count change in the working tree; batch code was unchanged from main.

Eager submission has linear retained memory, and extreme batch sizes remain a
reasonable future target. At the smaller sizes measured here, parent overhead
is small relative to real SDR work. This experiment establishes no process-pool
throughput improvement for a bounded replacement. Bounding also changes which
queued side effects can execute after the first failure under stop-on-error;
that scheduling contract needs explicit coverage before changing submission.
No batch production change is justified by these measurements alone.

The exact parent-only experiment is reproduced below. It intentionally replaces
the executor, not the batch implementation. Run with the project interpreter
and `PYTHONHASHSEED=0`; its output is a JSON sample record.

```python
import contextlib,io,json,logging,statistics,tempfile,time,tracemalloc
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch
import cja_auto_sdr.generator as g
from cja_auto_sdr.pipeline.batch import BatchProcessor
class ImmediatePool:
 def __init__(self,**kwargs): pass
 def __enter__(self): return self
 def __exit__(self,*args): pass
 def submit(self,fn,args):
  f=Future(); f.set_result(SimpleNamespace(data_view_id=args.data_view_id,success=True,duration=0)); return f
logger=logging.getLogger('batch-bench');logger.disabled=True
report=[]
with tempfile.TemporaryDirectory() as directory, patch.object(g,'setup_logging',return_value=logger),patch.object(g,'ProcessPoolExecutor',ImmediatePool),patch.object(BatchProcessor,'print_summary'),contextlib.redirect_stdout(io.StringIO()):
 for n in [10,100,1000,10000]:
  processor=BatchProcessor(output_dir=directory,quiet=True,workers=4)
  ids=[f'dv_{i}' for i in range(n)]
  samples=[]
  for _ in range(7):
   start=time.perf_counter();r=processor.process_batch(ids);samples.append(time.perf_counter()-start)
   assert len(r['successful'])==n
  tracemalloc.start();r=processor.process_batch(ids);peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
  report.append({'jobs':n,'median_seconds':statistics.median(samples),'samples':samples,'peak_python_bytes':peak})
open('/tmp/cja-batch-before.json','w').write(json.dumps(report,indent=2))
```

## Shared-cache proxy contention: deferred

The workload harness measures local validation-cache miss/hit behavior, not
Manager-proxy IPC, process contention or org-report disk-cache behavior. Its
local cache benefit does not establish a shared-cache bottleneck. Changing IPC
or cache policy without measured hit rates and contention would be speculative.
The existing warm-cache single-validation optimization remains intact.
