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

- **`cja_sdr_generate`**: `data_view_id` is always required. `format` accepts the direct formats plus the CLI aliases `all`, `reports`, `data`, and `ci`. Main SDR artifacts still use `output_dir` auto-naming. Standalone `quality_report` mode additionally honors `output` for stdout or a caller-chosen file path, and falls back to `output_dir` for auto-named report files when `output` is omitted.
- **`cja_sdr_discover`**: `data_view_id` is required only for `describe_dataview`, `list_metrics`, `list_dimensions`, `list_segments`, `list_calculated_metrics`. It is unused for `list_dataviews`, `list_connections`, `list_datasets`.
- **`cja_sdr_diff`**: `source`/`target` apply to `diff`. `compare_snapshots_source`/`compare_snapshots_target` apply to `compare_snapshots`. `snapshot` applies to `diff_snapshot`. `compare_with_prev` requires only a data view ID (passed as `source`). `output` is for stdout JSON only. `diff_output` is limited to inline-text output such as `console` or `format_pr_comment: true`; file-writing formats (`json`, `markdown`, `html`, `excel`, `csv`) create auto-named artifacts under `output_dir`.
- **`cja_sdr_governance`**: `duplicate_threshold` is an integer count of high-similarity pairs. `isolated_threshold` is a `0.0-1.0` percentage. `output` can target stdout or a named location, but the shape depends on `format`: JSON/Excel/Markdown/HTML create a single file, CSV expands to a directory of multiple files, and console ignores named file paths. `output_dir` controls auto-named artifacts.
- **`cja_sdr_config`**: `config_json` applies only to `config_status`.

---

## Agent Mode (`agent_mode`)

`agent_mode` is a wrapper convenience that maps to the CLI's `--agent-mode` preset:

```text
--format json --output - --log-format json
```

Important caveats:

- It expands to the repo's real CLI contract; it is not an independent execution mode.
- Explicit manifest parameters still win over the preset.
- Command-family behavior still follows the underlying CLI implementation. Discovery, diff, and org-report flows honor stdout JSON directly. Single-SDR generation still writes auto-named SDR artifacts under `output_dir`, while standalone `quality_report` mode continues to honor `output`/`output_dir`.

---

## stdout vs. File Output

- `cja_sdr_generate`: main SDR artifacts use `output_dir` auto-naming. Standalone `quality_report` mode supports `output: "-"` / `output: "stdout"` for JSON or CSV stdout, a caller-chosen file path in `output`, or an auto-named report under `output_dir`.
- `cja_sdr_diff`: use `output: "-"` or `output: "stdout"` for JSON stdout. `diff_output` is only for inline-text output such as `console` or `format_pr_comment: true`; JSON/Markdown/HTML/Excel/CSV file outputs remain auto-named under `output_dir`.
- `cja_sdr_governance`: use `output: "-"` or `output: "stdout"` for supported stdout flows. For named outputs, JSON/Excel/Markdown/HTML create a single file, CSV creates a directory of multiple files, and console ignores named file paths. Use `output_dir` for auto-named artifacts.
- Use `run_summary_json` to capture a stable machine-readable completion record at a known path regardless of primary output behavior.

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
    "output_dir": "/tmp/reports",
    "fail_on_quality": "HIGH",
    "run_summary_json": "/tmp/run_summary.json",
    "profile": "prod"
  }
}
```

For a standalone quality-report-only flow, set `quality_report` to `json` or `csv` and use `output` for stdout or a stable report path.

---

## Example: Generic Wrapper Construction

For a non-LLM wrapper that reads these manifests and shells out to the CLI:

1. Load the manifest JSON for the target command family.
2. Validate the caller payload against `parameters.properties` and any documented command-specific applicability rules.
3. Convert `snake_case` parameter names to CLI flags (`run_summary_json` → `--run-summary-json`).
4. Emit booleans as presence/absence flags, not string values (`agent_mode: true` → `--agent-mode`).
5. Preserve exact IDs and snapshot file paths as documented instead of guessing by name.
6. Execute `uv run cja_auto_sdr ...` and consume stdout/stderr according to the command family's documented output contract.

Minimal example:

```text
payload = {"command": "list_dataviews", "agent_mode": true, "format": "json"}
argv = ["uv", "run", "cja_auto_sdr", "--list-dataviews", "--agent-mode", "--format", "json"]
```

---

## Notes for Manifest Consumers

- `show_config` (interactive config display) is intentionally excluded from all manifests — it is not suitable for automated use.
- All `enum` values mirror the exact CLI flag values (e.g. `"INFO"`, `"LOW"` for `fail_on_quality`).
- Boolean parameters map to presence/absence of the corresponding CLI flag (e.g. `agent_mode: true` → `--agent-mode`).
- Parameter names use `snake_case`; CLI flags use `kebab-case` (e.g. `run_summary_json` → `--run-summary-json`).
