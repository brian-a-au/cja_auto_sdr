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
- Any time a data view's quality score needs to be measured and reported

## Inputs

**Required:**
- `<dv_id>` — the data view ID to quality-check (or `--org-report` for all views)
- `CJA_CLIENT_ID`, `CJA_CLIENT_SECRET`, `CJA_ORG_ID` — API credentials

**Optional:**
- `--fail-on-quality` — exit non-zero if any quality threshold is breached
- `--format json` — machine-readable output for pipeline consumption
- `--output <path>` — write quality report to file
- `--profile <name>` — named credential profile
- `--workers <n>` — parallel API workers (default: auto-tuned)

## Constraints

- Quality checks are read-only; this playbook does not remediate issues.
- `--fail-on-quality` uses built-in thresholds; custom thresholds are configured
  via the profile or config file, not per-invocation flags.
- Org-wide quality checks (`--org-report`) may be slow for large organizations;
  plan for several minutes of runtime and use `--workers` to optimize.
- Missing descriptions and empty display names are the most common quality
  findings; prepare remediation scripts separately.

## Primary CLI Flows

**1. Quality gate for a single data view (unattended CI):**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> --agent-mode \
  --fail-on-quality \
  --format json \
  --output /tmp/quality-report.json
echo "Exit: $?"
```

Exit 0 — all quality thresholds passed.
Exit 2 — quality threshold breached; inspect `quality` section of JSON output.
Exit 64 — authentication failure.

**2. Org-wide quality sweep:**

```bash
uv run cja_auto_sdr --org-report --agent-mode \
  --fail-on-quality \
  --format json \
  --output /tmp/org-quality.json
```

**3. Parse quality findings from JSON output:**

The `quality` object in the report includes:
- `score`: 0–100 composite quality score
- `findings`: array of issues, each with `severity`, `code`, `component_id`, `message`
- `thresholds_breached`: boolean

Filter `findings` where `severity == "critical"` for blocking issues.
Filter `severity == "warning"` for advisory items.

**4. Generate a human-readable quality report:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> --agent-mode \
  --fail-on-quality \
  --format markdown \
  --output /tmp/quality-report.md
```

## Success Criteria

- Exit code 0 from the quality-check command.
- `quality.thresholds_breached` is `false` in JSON output.
- `quality.score` meets or exceeds the configured minimum (default: 70).
- No `critical` findings in the `quality.findings` array.

## Follow-Up Actions

- **Thresholds breached (exit 2):** Block the pipeline; route `quality.findings`
  to schema owners for remediation. Reference component IDs for targeted fixes.
- **Warnings only (exit 0):** Log findings; schedule remediation for next sprint.
- **Clean pass:** Record quality score and timestamp; optionally commit a snapshot
  via `snapshot-manager.md` to track score trends over time.
- **Recurring monitoring:** Pair with `sdr-auditor.md` for governance context and
  `diff-reviewer.md` to detect quality regressions between releases.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
