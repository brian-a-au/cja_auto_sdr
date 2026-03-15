# AGENTS.md — CJA Auto SDR Tool Contract

`cja_auto_sdr` generates Solution Design Reference (SDR) documentation from Adobe Customer Journey Analytics data views.

---

## Setup

```bash
uv sync
```

### Auth: Environment Variables

| Variable   | Required | Description            |
|------------|----------|------------------------|
| `ORG_ID`   | Yes      | Adobe Organization ID  |
| `CLIENT_ID`| Yes      | OAuth Client ID        |
| `SECRET`   | Yes      | Client Secret          |
| `SCOPES`   | Yes      | OAuth scopes (from Adobe Developer Console) |
| `SANDBOX`  | No       | Sandbox name           |

### Auth: Profile Alternative

```bash
uv run cja_auto_sdr --profile-add <name>   # create interactively
uv run cja_auto_sdr --profile <name> ...   # use profile
export CJA_PROFILE=<name>                  # set default
```

Profiles stored in `~/.cja/orgs/<name>/`. Profile overrides env vars.

---

## Command Reference

### Discovery

```bash
uv run cja_auto_sdr --list-dataviews [--format json|csv] [--output -]
uv run cja_auto_sdr --list-connections [--format json|csv] [--output -]
uv run cja_auto_sdr --list-datasets [--format json|csv] [--output -]
```

Supports `--filter PATTERN`, `--exclude PATTERN`, `--limit N`, `--sort FIELD`.

### Inspection (per data view)

```bash
uv run cja_auto_sdr <dv_id> --describe-dataview
uv run cja_auto_sdr <dv_id> --list-metrics    [--format json|csv] [--output -]
uv run cja_auto_sdr <dv_id> --list-dimensions [--format json|csv] [--output -]
uv run cja_auto_sdr <dv_id> --list-segments   [--format json|csv] [--output -]
uv run cja_auto_sdr <dv_id> --list-calculated-metrics [--format json|csv] [--output -]
uv run cja_auto_sdr <dv_id> --stats
```

`--list-metrics`, `--list-dimensions`, `--list-segments`, `--list-calculated-metrics` support `--filter`, `--exclude`, `--sort`, `--limit`.

### Generation

| Format value | Output produced                        |
|--------------|----------------------------------------|
| `excel`      | `.xlsx` workbook (default)             |
| `csv`        | CSV file(s)                            |
| `json`       | JSON file                              |
| `html`       | HTML report                            |
| `markdown`   | Markdown file                          |
| `all`        | All file formats + console             |
| `reports`    | Alias: excel + markdown                |
| `data`       | Alias: csv + json                      |
| `ci`         | Alias: json + markdown                 |

```bash
# Generate default Excel SDR
uv run cja_auto_sdr <dv_id>

# Machine-readable JSON to stdout
uv run cja_auto_sdr <dv_id> --format json --output -

# Write to specific directory
uv run cja_auto_sdr <dv_id> --format excel --output-dir /reports

# Batch: multiple data views
uv run cja_auto_sdr <dv_id1> <dv_id2> --format ci --continue-on-error

# Run summary for observability
uv run cja_auto_sdr <dv_id> --format json --run-summary-json -
```

### Comparison

```bash
# Live diff of two data views
uv run cja_auto_sdr --diff <dv1_id> <dv2_id> [--format json] [--output -]

# Save snapshot to file (convention: place dv_id before flags)
uv run cja_auto_sdr <dv_id> --snapshot <output_file.json>

# Compare data view against snapshot file
uv run cja_auto_sdr <dv_id> --diff-snapshot <snapshot_file.json>

# Compare against most recent snapshot in snapshot-dir
uv run cja_auto_sdr <dv_id> --compare-with-prev

# Compare two snapshot files (no API calls)
uv run cja_auto_sdr --compare-snapshots <file1.json> <file2.json>

# List snapshots
uv run cja_auto_sdr --list-snapshots [<dv_id>]

# Prune snapshots by retention policy
uv run cja_auto_sdr --prune-snapshots --keep-last 20 --keep-since 30d
```

Key flags: `--changes-only`, `--summary`, `--format json --output -`, `--warn-threshold PERCENT`,
`--auto-snapshot`, `--auto-prune`, `--snapshot-dir DIR`, `--keep-last N`, `--keep-since PERIOD`.

### Governance (Org-Wide)

```bash
# Basic org-wide report
uv run cja_auto_sdr --org-report [--format json] [--output -]

# With clustering
uv run cja_auto_sdr --org-report --cluster

# Force similarity matrix
uv run cja_auto_sdr --org-report --force-similarity

# CI/CD governance gates
uv run cja_auto_sdr --org-report --duplicate-threshold 5 --fail-on-threshold
uv run cja_auto_sdr --org-report --isolated-threshold 0.3 --fail-on-threshold

# Trending
uv run cja_auto_sdr --org-report --trending-window 10

# Compare to previous report
uv run cja_auto_sdr --org-report --compare-org-report prev.json
```

### Validation

```bash
# Validate config and API connectivity (no data view required)
uv run cja_auto_sdr --validate-config

# Dry-run: validate config without generating reports (requires dv_id)
uv run cja_auto_sdr <dv_id> --dry-run

# Machine-readable config status
uv run cja_auto_sdr --config-status --config-json
```

---

## Exit Codes

| Code | Meaning                                                                 | Agent Action                                      |
|------|-------------------------------------------------------------------------|---------------------------------------------------|
| `0`  | Success                                                                 | Continue; consume stdout output                   |
| `1`  | General error (auth, API failure, data view not found, I/O error)       | Abort; parse stderr JSON for `error`/`error_type` |
| `2`  | Policy threshold exceeded (diff changes found, quality gate, governance) | Flag for review; do not treat as crash            |
| `3`  | Diff warn-threshold exceeded (`--warn-threshold`)                       | Notify; optionally escalate                       |
| `130`| KeyboardInterrupt (SIGINT)                                              | Treat as cancelled; retry if appropriate          |

Exit code 1 takes precedence over 2 if both conditions apply.

---

## Output Conventions

- Use `--format json --output -` for machine-parseable stdout.
- Only `json` and `csv` formats are valid with `--output -` (stdout).
- `--output -` implies `--quiet` (suppresses banner/progress to stderr).
- For scheduled/agent runs, prefer retry settings such as `--max-retries 5 --retry-max-delay 60` to absorb transient Adobe API rate limits.
- On failure, stderr receives a JSON error envelope:
  ```json
  {"error": "Configuration error: Missing credentials", "error_type": "configuration_error"}
  ```
- `--run-summary-json -` writes a structured run summary to stdout regardless of output format.

---

## File Conventions

| Artifact          | Location                          | Override flag        |
|-------------------|-----------------------------------|----------------------|
| SDR reports       | Current directory (default)       | `--output-dir PATH`  |
| Snapshots         | `./snapshots/`                    | `--snapshot-dir DIR` |
| Log output        | stderr (structured or text)       | `--log-level`, `--log-format json` |
| Org-report cache  | `~/.cja_auto_sdr/cache/`          | n/a                  |
| Profiles          | `~/.cja/orgs/<name>/`             | `--profile`, `CJA_PROFILE`, `CJA_HOME` |

Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Log formats: `text` (default), `json`.

---

## See Also

- [`docs/AGENT_AUTOMATION.md`](docs/AGENT_AUTOMATION.md) — scheduling patterns, agent framework integration, notifications, security
- [`scripts/orchestrator.py`](scripts/orchestrator.py) — multi-org orchestration script
- [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md) — full human-facing CLI documentation
- [`docs/DIFF_COMPARISON.md`](docs/DIFF_COMPARISON.md) — snapshot and diff deep-dive
- [`docs/ORG_WIDE_ANALYSIS.md`](docs/ORG_WIDE_ANALYSIS.md) — governance analysis guide
- [`docs/FAILURE_CODES.md`](docs/FAILURE_CODES.md) — stable `failure_code` registry for `--run-summary-json`
