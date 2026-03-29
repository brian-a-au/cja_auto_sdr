# Onboarding Guide

## Purpose

Walks through first-run setup for a new CJA SDR Generator installation,
validates credentials and API access, discovers available data views, and
generates an initial SDR for a target data view. Establishes a baseline
snapshot for future diff comparisons.

## When To Use

- Initial setup on a new machine or CI environment
- Onboarding a new Adobe CJA organization or workspace
- Verifying that credentials and API connectivity are functional after rotation
- Generating a first baseline SDR before any automated workflows begin

## Inputs

**Required:**
- `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES` — Adobe IMS credentials
  (set as environment variables or in a `.env` file)

**Optional:**
- `--profile-add <name>` — create a named profile for multi-org environments
- `--profile <name>` — reuse an existing named profile
- `<dv_id>` — a specific data view ID to target for the initial SDR; if
  unknown, use `--list-dataviews` to discover available IDs
- `--output-dir <path>` — directory for auto-named SDR artifacts
- `--run-summary-json <path>` — stable machine-readable completion metadata
- `--format excel` | `json` | `csv` | `markdown` — output format

## Constraints

- Requires network access to the Adobe CJA API (`analytics.adobe.io`).
- Credentials must have read access to at least one data view.
- Does not create or modify CJA configurations.
- The `--validate-config` flag verifies credentials without generating output;
  it is a prerequisite check, not a full SDR generation step.

## Primary CLI Flows

**1. Validate credentials and API connectivity:**

```bash
uv run cja_auto_sdr --validate-config
echo "Exit: $?"
```

Exit 0 — credentials valid, API reachable.
Exit 1 — validation failed; verify `CLIENT_ID` / `SECRET` / `ORG_ID` / `SCOPES`.

**2. Discover available data views:**

```bash
uv run cja_auto_sdr --list-dataviews --format json
```

Note the `id` field for each data view. Use these IDs (not display names) in
all subsequent automation steps.

**3. Inspect a target data view before generating the SDR:**

```bash
uv run cja_auto_sdr --describe-dataview <DATA_VIEW_ID>
```

**4. Generate the initial SDR:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> --agent-mode \
  --output-dir /tmp/reports \
  --run-summary-json /tmp/initial-sdr-run-summary.json
echo "Exit: $?"
```

This writes the SDR artifact under `/tmp/reports` and records completion metadata
in `/tmp/initial-sdr-run-summary.json`.

**5. Capture a baseline snapshot for future comparisons:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> --snapshot ./snapshots/<DATA_VIEW_ID>_baseline.json
```

This snapshot can be used with `diff-reviewer.md` to detect future changes.

**6. (Optional) Save a named profile for reuse:**

```bash
uv run cja_auto_sdr --profile-add production
```

Follow the interactive prompts to store credentials. Subsequent commands can
use `--profile production` instead of environment variables.

## Success Criteria

- `--validate-config` exits 0.
- `--list-dataviews` returns at least one data view.
- SDR generation exits 0 and writes an auto-named artifact under the requested `--output-dir`.
- Baseline snapshot is recorded (verify with `--list-snapshots`).

## Follow-Up Actions

- Store credentials in a secrets manager or CI secret store; do not commit to version control.
- Schedule `sdr-auditor.md` for recurring org-wide governance reviews.
- Configure `snapshot-manager.md` to capture snapshots on a regular cadence.
- Document the baseline SDR path and snapshot file path for the team.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
