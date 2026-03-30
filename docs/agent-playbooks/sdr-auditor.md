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
- `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES` — API credentials (env or profile)

**Optional:**
- `--profile <name>` — named credential profile (overrides env vars)
- `--agent-mode` — machine-readable JSON on stdout (recommended for automation)
- `--duplicate-threshold <n>` — maximum allowed high-overlap pairs
- `--isolated-threshold <percent>` — maximum isolated-component percentage
- `--fail-on-threshold` — exit 2 when a configured governance threshold is exceeded
- `--trending-window <n>` — include drift analysis across the last N cached org-report snapshots

## Constraints

- Does not modify any data views or CJA configurations.
- Does not auto-remediate quality issues; it only reports them.
- Requires read access to all target data views; inaccessible views are logged and skipped.
- Large orgs (100+ data views) may take several minutes; use `--workers` to tune parallelism.
- Threshold-based exits are driven by governance thresholds, not by advisory severity alone.

## Primary CLI Flows

**1. Full org audit with JSON output (unattended):**

```bash
uv run cja_auto_sdr --org-report --agent-mode > /tmp/org-audit.json
echo "Exit: $?"
```

Exit 0 — audit complete.
Exit 1 — configuration, auth, or processing failure.

**2. Audit with governance threshold enforcement:**

```bash
uv run cja_auto_sdr --org-report --agent-mode \
  --duplicate-threshold 5 \
  --fail-on-threshold > /tmp/org-audit.json
```

**3. Triage advisories from JSON output:**

Parse the `advisories.findings` array from the JSON report. Each finding has:
- `type`
- `severity`
- `message`
- `details`
- `recommended_actions`

Filter `severity == "critical"` for immediate action items.

**4. Target a specific data view for deep audit:**

```bash
uv run cja_auto_sdr <dv_id> \
  --quality-report json \
  --output /tmp/dv-audit.json \
  --fail-on-quality HIGH
```

## Success Criteria

- Exit code 0 means the default org-report run completed.
- If `--fail-on-threshold` is used, exit code 2 indicates a configured governance threshold breach.
- JSON output is valid and reports at least one analyzed data view.
- If `--fail-on-threshold` is used, exit 0 means the configured governance thresholds passed.
- Advisory findings are present and parseable when issues are detected.
- Output file written to the expected path when stdout is redirected or a per-view quality report path is specified.

## Follow-Up Actions

- **Critical advisories:** Open tickets for each affected data view; assign to schema owners.
- **Warning advisories:** Log for next scheduled review; do not block pipeline.
- **Clean audit:** Record timestamp and commit snapshot for drift tracking (see `snapshot-manager.md`).
- **Recurring audits:** Schedule this playbook on a cron or CI trigger; compare results with previous run using `diff-reviewer.md`.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
