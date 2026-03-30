# Quality Monitor

## Purpose

Enforces data quality gates against CJA data views, generates quality reports
with severity-classified findings, and integrates quality checks into CI/CD
pipelines or scheduled monitoring workflows. Fails fast on critical violations
to prevent downstream data issues.

## When To Use

- CI gate before promoting a data view schema change to production
- Scheduled quality sweeps (daily or per-deployment)
- Post-migration validation to confirm component descriptions and metadata are intact
- Any time a data view's quality issues need to be measured and reported

## Inputs

**Required:**
- One or more exact data view IDs (`<dv_id> [<dv_id> ...]`)
- `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES` — API credentials (or `--profile <name>`)

**Optional:**
- `--fail-on-quality <SEVERITY>` — exit 2 if any issue at or above the threshold is found
- `--quality-report json|csv` — emit a standalone quality report without SDR artifacts
- `--output <path>` — write quality report to file
- `--profile <name>` — named credential profile
- `--workers <n>` — parallel API workers (default: auto-tuned)

## Constraints

- Quality checks are read-only; this playbook does not remediate issues.
- `--quality-report` supports `json` and `csv` only.
- `--fail-on-quality` is supported in SDR/quality-report flows, not with `--org-report`.
- Org-wide sweeps require a resolved list of data view IDs; start with discovery if needed.
- Missing descriptions and empty display names are the most common quality
  findings; prepare remediation scripts separately.

## Primary CLI Flows

**1. Quality gate for a single data view (unattended CI):**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> \
  --quality-report json \
  --output /tmp/quality-report.json \
  --fail-on-quality HIGH
echo "Exit: $?"
```

Exit 0 — all quality thresholds passed.
Exit 2 — quality threshold breached; inspect the emitted issue rows in the JSON report.
Exit 1 — configuration, auth, or processing failure.

**2. Org-wide quality sweep:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID_1> <DATA_VIEW_ID_2> <DATA_VIEW_ID_3> \
  --quality-report json \
  --output /tmp/org-quality.json \
  --continue-on-error
```

**3. Parse quality findings from JSON output:**

Standalone quality-report JSON is an array of issue objects. Inspect fields such as:
- `Severity`
- `Issue`
- `Data View ID`
- `Data View Name`
- `Type`

Filter rows where `Severity == "CRITICAL"` for blocking issues.
Filter rows where `Severity == "HIGH"`, `Severity == "MEDIUM"`, `Severity == "LOW"`, or `Severity == "INFO"` for advisory review.

**4. Generate a human-readable quality report:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> \
  --format markdown \
  --output-dir /tmp/reports \
  --fail-on-quality HIGH \
  --run-summary-json /tmp/quality-run-summary.json
```

## Success Criteria

- Exit code 0 from the quality-check command.
- The standalone quality report is valid JSON or CSV and is non-empty.
- No report entries meet or exceed the configured `--fail-on-quality` threshold.
- If a run summary is written, `quality_gate_failed` is `false`.

## Follow-Up Actions

- **Thresholds breached (exit 2):** Block the pipeline; route the emitted issue rows
  to schema owners for remediation. Reference the affected `Data View ID` and issue rows for targeted fixes.
- **Warnings only (exit 0):** Log findings; schedule remediation for next sprint.
- **Clean pass:** Record the issue counts by severity and timestamp; optionally commit a snapshot
  via `snapshot-manager.md` to track trend changes over time.
- **Recurring monitoring:** Pair with `sdr-auditor.md` for governance context and
  `diff-reviewer.md` to detect quality regressions between releases.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
