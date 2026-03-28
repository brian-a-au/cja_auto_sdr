# CJA Auto SDR — Tool Manifests

This directory contains OpenAI-style JSON function definitions (tool manifests) for integrating `cja_auto_sdr` into agent frameworks (OpenAI function calling, Anthropic tool use, LangChain, etc.).

## Manifest Overview

| File | Tool Name | Purpose |
|------|-----------|---------|
| `cja_sdr_generate.json` | `cja_sdr_generate` | Generate an SDR document for a single data view |
| `cja_sdr_discover.json` | `cja_sdr_discover` | Discover and inspect CJA resources (data views, connections, datasets) |
| `cja_sdr_config.json` | `cja_sdr_config` | Configuration preflight and status checks |
| `cja_sdr_diff.json` | `cja_sdr_diff` | Compare data view snapshots and detect schema drift |
| `cja_sdr_governance.json` | `cja_sdr_governance` | Org-wide governance reporting and drift detection |

---

## Command-Family Applicability

Not every manifest parameter is valid for every command within a family. The `command` enum in each manifest determines which other parameters are applicable:

- **`cja_sdr_discover`**: `data_view_id` is required only for `describe_dataview`, `list_metrics`, `list_dimensions`, `list_segments`, `list_calculated_metrics`. It is unused for `list_dataviews`, `list_connections`, `list_datasets`.
- **`cja_sdr_diff`**: `source`/`target` apply to `diff`. `compare_snapshots_source`/`compare_snapshots_target` apply to `compare_snapshots`. `snapshot` applies to `diff_snapshot`. `compare_with_prev` requires only a data view ID (passed as `source`).
- **`cja_sdr_config`**: `config_json` applies only to `config_status`.

---

## Agent Mode (`agent_mode`)

All generation and reporting tools accept an `agent_mode` boolean. When `true`:

- Banners, progress bars, and human-readable noise are suppressed.
- Structured JSON is emitted to **stdout** (rather than formatted for a terminal).
- Errors are written to **stderr** as JSON objects with `error`, `code`, and `details` fields.

**Always set `agent_mode: true` in automated pipelines.**

CLI mapping: `agent_mode: true` → `--agent-mode` flag.

---

## stdout vs. File Output

- When `output` is omitted, the tool writes to **stdout**. Combine with `agent_mode: true` and `format: "json"` to receive structured, parseable output directly from the tool call.
- When `output` is provided, the file is written to that path and a confirmation summary is emitted to stdout.
- Use `run_summary_json` to always capture a machine-readable run summary at a known file path, regardless of where primary output goes.

---

## `run-summary-json` Usage

The `run_summary_json` parameter (CLI: `--run-summary-json <path>`) writes a JSON file after the command completes containing:

```json
{
  "exit_code": 0,
  "duration_seconds": 4.2,
  "data_view_id": "dv_abc123",
  "component_counts": { "metrics": 42, "dimensions": 118 },
  "quality_issues": 3,
  "timestamp": "2026-03-28T10:00:00Z"
}
```

This is the recommended integration point for orchestrators and CI systems that need structured outcome data without parsing stdout.

---

## Config Preflight Flows

Before running generation or governance commands in an automated pipeline, use `cja_sdr_config` to verify connectivity:

1. Call `cja_sdr_config` with `command: "validate_config"` and the target `profile`.
2. If it returns a non-zero exit code, abort and surface the error — credentials or connectivity are not ready.
3. Optionally call `config_status` with `config_json: true` to log the effective configuration for audit purposes.
4. Proceed with `cja_sdr_generate` or `cja_sdr_governance`.

The `--validate-config` CLI flag performs a lightweight credential resolution and API ping — it does not generate any SDR output.

---

## `scripts/orchestrator.py` Scope

`scripts/orchestrator.py` is a **subprocess-based orchestration helper** for programmatic automation from Python. It is distinct from agent tool calling:

- It manages subprocess invocations of `cja_auto_sdr` CLI commands.
- It is appropriate for batch pipelines, CI scripts, and Python-native orchestration.
- For LLM agent frameworks, prefer the tool manifests in this directory over direct subprocess invocation.

The tool manifests here complement `orchestrator.py` — they describe the *interface*, while `orchestrator.py` handles *subprocess execution mechanics*.

---

## Exact-ID Guidance

All data view IDs (`data_view_id`, `source`, `target`) must be **exact CJA data view IDs**, not display names. Data view IDs begin with `dv_` followed by an alphanumeric string.

Use `cja_sdr_discover` with `command: "list_dataviews"` to enumerate available data view IDs before calling generation or diff commands.

---

## Example: Tool Calling Sequence

A typical agent workflow for generating a governed SDR:

```json
// Step 1: Preflight — validate config
{
  "tool": "cja_sdr_config",
  "parameters": {
    "command": "validate_config",
    "profile": "prod"
  }
}

// Step 2: Discovery — find the right data view
{
  "tool": "cja_sdr_discover",
  "parameters": {
    "command": "list_dataviews",
    "format": "json",
    "agent_mode": true,
    "profile": "prod"
  }
}

// Step 3: Generate SDR with quality gate
{
  "tool": "cja_sdr_generate",
  "parameters": {
    "data_view_id": "dv_abc123xyz",
    "format": "json",
    "agent_mode": true,
    "quality_report": "json",
    "fail_on_quality": "HIGH",
    "run_summary_json": "/tmp/run_summary.json",
    "profile": "prod"
  }
}
```

---

## Notes for Manifest Consumers

- `show_config` (interactive config display) is intentionally excluded from all manifests — it is not suitable for automated use.
- All `enum` values mirror the exact CLI flag values (e.g. `"INFO"`, `"LOW"` for `fail_on_quality`).
- Boolean parameters map to presence/absence of the corresponding CLI flag (e.g. `agent_mode: true` → `--agent-mode`).
- Parameter names use `snake_case`; CLI flags use `kebab-case` (e.g. `run_summary_json` → `--run-summary-json`).
