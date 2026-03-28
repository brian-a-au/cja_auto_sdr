# Diff Reviewer

## Purpose

Reviews schema changes between two CJA data view snapshots, identifies
breaking changes and regressions, and produces a structured advisory report.
Supports both point-in-time comparisons and sliding-window drift detection.

## When To Use

- After a deployment or schema migration to verify expected changes only
- Before approving a pull request that touches data view configurations
- Scheduled drift detection to catch unannounced changes
- Any time two snapshots need to be compared for audit or compliance purposes

## Inputs

**Required (point-in-time diff):**
- `<source>` and `<target>` — snapshot labels or file paths
- `CJA_CLIENT_ID`, `CJA_CLIENT_SECRET`, `CJA_ORG_ID` — API credentials

**Required (compare with previous):**
- `<dv_id>` — data view ID to compare against its most recent snapshot
- An existing snapshot created by `snapshot-manager.md`

**Optional:**
- `--format json` — machine-readable output (recommended for automation)
- `--output <path>` — write diff report to file
- `--fail-on-advisory breaking` — non-zero exit on breaking changes
- `--profile <name>` — named credential profile

## Constraints

- Requires at least one prior snapshot to exist for `--compare-with-prev`.
- Does not create snapshots; use `snapshot-manager.md` for that step.
- Does not modify CJA data views.
- Renamed components may appear as add+remove pairs rather than renames.

## Primary CLI Flows

**1. Compare two named snapshots (unattended):**

```bash
uv run cja_auto_sdr --diff baseline current --agent-mode \
  --format json \
  --output /tmp/diff-report.json
echo "Exit: $?"
```

Exit 0 — diff complete, no breaking changes detected.
Exit 2 — breaking changes present (when `--fail-on-advisory breaking` is set).

**2. Compare a data view against its previous snapshot:**

```bash
uv run cja_auto_sdr <dv_id> --compare-with-prev --agent-mode \
  --format json \
  --output /tmp/diff-report.json
```

**3. Drift detection over a time window:**

```bash
uv run cja_auto_sdr --org-report --trending-window 30 --agent-mode \
  --format json \
  --output /tmp/drift-report.json
```

**4. Parse diff output for breaking changes:**

From the JSON report, inspect the `diff.changes` array. Breaking changes have
`breaking: true`. Fields of interest:
- `change_type`: `"removed"` | `"modified"` | `"added"`
- `component`: component type and ID
- `breaking`: boolean
- `advisory_code`: machine-readable code for downstream routing

## Success Criteria

- Exit code 0 from the diff command.
- JSON output is valid and contains a `diff` key.
- If `breaking_changes_count == 0`, the schema is stable.
- Any breaking changes are routed to the appropriate escalation workflow.

## Follow-Up Actions

- **Breaking changes found:** Block deployment; notify schema owners with the diff report path.
- **Non-breaking changes:** Log for audit trail; proceed with deployment.
- **No changes:** Confirm snapshot is up to date; no action needed.
- **Recurring drift detection:** Pair with `snapshot-manager.md` to capture and compare snapshots on a schedule.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
