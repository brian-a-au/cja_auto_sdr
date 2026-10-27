# Failure Code Registry

Stable `failure_code` values used in `--run-summary-json` results.

Source of truth in code: `src/cja_auto_sdr/generator.py` `FAILURE_CODE_REGISTRY`.

| Failure Code | Meaning |
|---|---|
| `CJA_INIT_FAILED` | CJA client/configuration initialization failed before data retrieval. |
| `DATAVIEW_LOOKUP_INVALID` | Data view lookup payload was invalid or did not pass validation checks. |
| `COMPONENT_FETCH_FAILED` | Required component endpoint fetch failed (for example metrics or dimensions transport/runtime failure, or an API error response such as HTTP 403 or 500). An error response is no longer read as an empty component list. |
| `REQUIRED_COMPONENTS_EMPTY` | Required component sets were both empty and run was fail-closed. |
| `DQ_VALIDATION_RUNTIME_FAILED` | Data-quality validation failed due to runtime/processing failure. |
| `OUTPUT_PERMISSION_DENIED` | Output write failed due to filesystem permission error. |
| `OUTPUT_WRITE_FAILED` | Output write failed due to non-permission I/O or serialization error. |
| `BATCH_WORKER_EXCEPTION` | Batch worker raised an exception at the worker boundary. |
| `UNEXPECTED_RUNTIME_ERROR` | Unhandled runtime exception surfaced at top-level data-view processing boundary. |
| `UNCLASSIFIED_FAILURE` | Legacy/unknown failure mapping fallback when no stable code was provided. |

## Compatibility

- These values are intended to be stable for automation and alerting.
- New codes may be added in future releases; consumers should ignore unknown values safely.
