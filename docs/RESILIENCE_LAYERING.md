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

### Upstream-failure signaling set (v3.5.14+)

```python
UPSTREAM_ADAPTER_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
```

This mirrors cjapy's `status_forcelist`. A payload that reaches the project
layer carrying one of these codes is an *adapter-exhausted* failure: cjapy
already retried and gave up. The retry wrapper handles it as follows:

- does **not** retry again (that would stack on top of the adapter)
- does **not** emit the `✓ … succeeded on attempt …` log even if prior attempts
  raised — the final return is not a success
- **does** call `circuit_breaker.record_failure(...)` so repeated upstream 5xx/
  429 trips the breaker and blocks further traffic until recovery

Non-upstream-failure HTTP error codes (e.g. 401/403/404/400/422) are caller
errors, not infrastructure distress; the breaker records them as successes
(the endpoint answered, so infrastructure is healthy) and the caller-side
classifier in `ParallelAPIFetcher._normalize_component_payload()` renders
the payload-level failure detail.

### Circuit breaker contract

`CircuitBreaker.record_failure()` is called **once per logical failure**:

- once per retry loop that exhausts its budget and raises (408 loop, network
  error loop, non-retryable exception)
- once per adapter-exhausted pass-through whose status is in
  `UPSTREAM_ADAPTER_STATUS_CODES`

It is **not** called once per retry attempt, and it is **not** called for
non-upstream-failure returns (2xx/3xx, or 4xx outside the upstream-failure
set).

### Non-overlap contract summary

| Status | Owner           | Behavior                                                                  |
| ------ | --------------- | ------------------------------------------------------------------------- |
| 408    | project layer   | `make_api_call_with_retry` retries with jitter; exhaustion → breaker failure |
| 429    | cjapy adapter   | upstream retries; project passes through; breaker records failure         |
| 500    | cjapy adapter   | upstream retries; project passes through; breaker records failure         |
| 502    | cjapy adapter   | upstream retries; project passes through; breaker records failure         |
| 503    | cjapy adapter   | upstream retries; project passes through; breaker records failure         |
| 504    | cjapy adapter   | upstream retries; project passes through; breaker records failure         |
| 4xx (other) | caller       | returned as-is; classified by caller; breaker records success (no failure)|

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

v3.5.14 fixes all five points:

1. Retry-wrapper status extraction recognizes `statusCode`, nested
   `error.statusCode`, and `response.statusCode`.
2. `RETRYABLE_STATUS_CODES` is narrowed to `{408}` so project retries are
   disjoint from cjapy adapter retries.
3. `ParallelAPIFetcher` classifies component payloads via
   `assess_component_payload()` before success accounting.
4. `initialize_cja()` and the dry-run `getDataViews()` probe only log
   success for list/tuple/DataFrame payloads; error-shaped dicts warn.
5. Adapter-exhausted pass-through payloads (status in
   `UPSTREAM_ADAPTER_STATUS_CODES`) record a circuit-breaker failure and
   suppress the success-after-retry log. Before v3.5.14 they were silently
   recorded as breaker successes, so repeated upstream 5xx/429 never tripped
   the circuit even though caller-side classifiers already treated the
   payloads as failures.
