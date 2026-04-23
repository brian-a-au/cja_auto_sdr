# Resilience Layering: cjapy Adapter vs. Project Retry Layer

This doc describes how retry handling is split between the upstream `cjapy`
library and the project's retry/circuit-breaker layer. It is the source of
truth for what statuses each layer owns and why.

## Upstream: `cjapy.connector.AdobeRequest`

`cjapy>=0.3.1` installs a session-level `urllib3.Retry` adapter inside
`AdobeRequest._build_session`:

| Setting                        | Value                              |
| ------------------------------ | ---------------------------------- |
| `total`                        | `max(max_retries, 3)`              |
| `status_forcelist`             | `[429, 500, 502, 503, 504]`        |
| `backoff_factor`               | `1`                                |
| `respect_retry_after_header`   | `True`                             |
| `raise_on_status`              | `False`                            |

Key consequences:

- For statuses in `status_forcelist`, the adapter retries internally with
  exponential backoff before returning a response. `Retry-After` headers are
  honored on 429.
- Because `raise_on_status=False`, when the adapter's budget is exhausted it
  returns the final error response rather than raising. `cjapy` request methods
  then call `res.json()` and **return the parsed JSON payload** — they do not
  return `requests.Response` objects, and they do not inject a snake_case
  `status_code` field into the returned dict.
- The payloads that reach the project layer therefore typically look like:

  ```json
  {"statusCode": 503, "message": "backend timeout"}
  ```

  with the status carried in camelCase `statusCode` (sometimes nested under
  `error` or `response`).

## Project layer: `cja_auto_sdr.api.resilience`

### Response-shape normalization

`make_api_call_with_retry()` uses `_extract_http_status_code_from_result()` to
recognize:

- attributes `status_code` and `statusCode` on response-like objects
- top-level mapping keys: `status_code`, `statusCode`, `status`, `http_status`,
  `httpStatus`, `code`
- the same keys nested under `error` or `response`

The helper reuses `coerce_http_status_code()` from
`cja_auto_sdr.core.discovery_exceptions`, so it rejects out-of-range or
non-numeric values.

### Retry-status set (v3.5.14+)

```python
RETRYABLE_STATUS_CODES: set[int] = {408}
```

Only 408 (Request Timeout) triggers a project-layer retry. This is the only
retryable status that is **not** in `cjapy`'s `status_forcelist`, so project
retries on 408 do not stack with upstream adapter retries.

For 429/500/502/503/504, `cjapy` has already retried before the response
reaches the project layer. Retrying again would:

- multiply total wait time (project backoff × upstream backoff already applied)
- exhaust CircuitBreaker budget faster than intended
- confuse debugging: a single logical failure shows up as many retries across
  two layers

These statuses therefore pass through the retry wrapper as ordinary return
values. Callers are expected to detect error-shaped payloads and handle them
appropriately — e.g. `ParallelAPIFetcher` now classifies them via
`assess_component_payload()` before recording a fetch as successful, and
`initialize_cja()` only reports connection success when `getDataViews()`
returns a list/tuple/DataFrame.

### Circuit breaker contract

`CircuitBreaker.record_failure()` is called **once per exhausted operation**,
not once per retry attempt. After `make_api_call_with_retry()` has used its
full budget and is about to raise, it records one breaker failure and raises.
Non-retryable exceptions also record one breaker failure and raise immediately.

### Non-overlap contract summary

| Status | Owner           | Behavior                                      |
| ------ | --------------- | --------------------------------------------- |
| 408    | project layer   | `make_api_call_with_retry` retries with jitter |
| 429    | cjapy adapter   | upstream retries; project passes through      |
| 500    | cjapy adapter   | upstream retries; project passes through      |
| 502    | cjapy adapter   | upstream retries; project passes through      |
| 503    | cjapy adapter   | upstream retries; project passes through      |
| 504    | cjapy adapter   | upstream retries; project passes through      |
| 4xx (other) | caller       | returned as-is; classified by caller          |

## Why this split exists

Before v3.5.14:

- The project retry wrapper detected statuses only via the snake_case
  `status_code` key, so actual `cjapy` payloads (`statusCode`) bypassed it.
- `RETRYABLE_STATUS_CODES` overlapped with `cjapy`'s `status_forcelist`,
  meaning the retry intent was duplicated on the few shapes that *did* go
  through the wrapper.
- `ParallelAPIFetcher._fetch_metrics()` and `_fetch_dimensions()` treated any
  non-empty dict payload as a successful fetch, so an error dict like
  `{"statusCode": 500, ...}` was logged as "success" with `item_count = 2`.
- `initialize_cja()` treated any non-`None` `getDataViews()` payload as a
  successful connection test.

v3.5.14 fixes all four points:

1. Retry-wrapper status extraction recognizes `statusCode`, nested
   `error.statusCode`, and `response.statusCode`.
2. `RETRYABLE_STATUS_CODES` is narrowed to `{408}` so project retries are
   disjoint from cjapy adapter retries.
3. `ParallelAPIFetcher` classifies component payloads via
   `assess_component_payload()` before success accounting.
4. `initialize_cja()` and the dry-run `getDataViews()` probe only log
   success for list/tuple/DataFrame payloads; error-shaped dicts warn.
