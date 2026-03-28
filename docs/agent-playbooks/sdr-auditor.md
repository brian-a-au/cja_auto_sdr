# SDR Auditor

## Purpose

Performs an org-wide governance review of all CJA data views, identifies data
quality issues and coverage gaps, and triages findings by severity. Produces
a structured advisory report suitable for automated decision-making or human
escalation.

## When To Use

- Scheduled governance sweeps (weekly, monthly)
- Pre-release validation before deploying schema changes
- Post-migration audits after onboarding new data views
- Any time a quality threshold violation is suspected org-wide

## Inputs

**Required:**
- `CJA_CLIENT_ID`, `CJA_CLIENT_SECRET`, `CJA_ORG_ID` — API credentials (env or profile)

**Optional:**
- `--profile <name>` — named credential profile (overrides env vars)
- `--output <path>` — write report to file instead of stdout
- `--format json` — machine-readable output (recommended for automation)
- `--fail-on-advisory critical` — non-zero exit when critical advisories present
- `--threshold-missing-description <n>` — flag data views where > n% of components lack descriptions

## Constraints

- Does not modify any data views or CJA configurations.
- Does not auto-remediate quality issues; it only reports them.
- Requires read access to all target data views; inaccessible views are logged and skipped.
- Large orgs (100+ data views) may take several minutes; use `--workers` to tune parallelism.

## Primary CLI Flows

**1. Full org audit with JSON output (unattended):**

```bash
uv run cja_auto_sdr --org-report --agent-mode \
  --format json \
  --output /tmp/org-audit.json
echo "Exit: $?"
```

Exit 0 — audit complete, no critical issues.
Exit 2 — critical advisories present (when `--fail-on-advisory critical` is set).
Exit 64 — authentication failure; check credentials.

**2. Audit with quality threshold enforcement:**

```bash
uv run cja_auto_sdr --org-report --agent-mode \
  --fail-on-quality \
  --format json \
  --output /tmp/org-audit.json
```

**3. Triage advisories from JSON output:**

Parse `advisories` array from the JSON report. Each entry has:
- `severity`: `"critical"` | `"warning"` | `"info"`
- `code`: machine-readable advisory code
- `data_view_id`: affected data view
- `message`: human-readable description

Filter `severity == "critical"` for immediate action items.

**4. Target a specific data view for deep audit:**

```bash
uv run cja_auto_sdr <dv_id> --agent-mode \
  --fail-on-quality \
  --format json \
  --output /tmp/dv-audit.json
```

## Success Criteria

- Exit code 0 from the org-report command.
- JSON output is valid and contains a `summary` key with `data_views_audited` > 0.
- No `critical` severity advisories in the output (or escalation workflow triggered if present).
- Output file written to the expected path (if `--output` was specified).

## Follow-Up Actions

- **Critical advisories:** Open tickets for each affected data view; assign to schema owners.
- **Warning advisories:** Log for next scheduled review; do not block pipeline.
- **Clean audit:** Record timestamp and commit snapshot for drift tracking (see `snapshot-manager.md`).
- **Recurring audits:** Schedule this playbook on a cron or CI trigger; compare results with previous run using `diff-reviewer.md`.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
