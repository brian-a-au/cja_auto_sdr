# Diff Reviewer

## Purpose

Reviews schema changes between two CJA data view snapshots, identifies
breaking changes and regressions, and produces a structured advisory report.
Supports file-to-file snapshot comparisons, compare-with-previous review for a
live data view, and org-report trending review across cached snapshots.

## When To Use

- After a deployment or schema migration to verify expected changes only
- Before approving a pull request that touches data view configurations
- Scheduled drift detection to catch unannounced changes
- Any time two snapshots need to be compared for audit or compliance purposes

## Inputs

**Required (point-in-time diff):**
- `<source_snapshot.json>` and `<target_snapshot.json>` — snapshot file paths
- No API credentials are required for `--compare-snapshots`

**Required (compare with previous):**
- `<dv_id>` — data view ID to compare against its most recent snapshot
- `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES` — API credentials (or `--profile <name>`)
- An existing snapshot created by `snapshot-manager.md`

**Optional:**
- `--agent-mode` — machine-readable JSON on stdout (recommended for automation)
- `--changes-only` — omit unchanged components
- `--warn-threshold <percent>` — return exit 3 when change volume exceeds the threshold
- `--output-dir <path>` — write auto-named diff artifacts for file formats such as markdown/html/excel/json
- `--profile <name>` — named credential profile

## Constraints

- `--compare-snapshots` is the snapshot-file workflow. `--diff` is reserved for
  comparing two live data view IDs.
- Requires at least one prior snapshot to exist for `--compare-with-prev`.
- Does not create snapshots; use `snapshot-manager.md` for that step.
- Does not modify CJA data views.
- Renamed components may appear as add+remove pairs rather than renames.

## Primary CLI Flows

**1. Compare two snapshot files (unattended):**

```bash
uv run cja_auto_sdr --compare-snapshots \
  ./snapshots/pre-migration.json \
  ./snapshots/post-migration.json \
  --agent-mode > /tmp/diff-report.json
echo "Exit: $?"
```

Exit 0 — comparison complete, no changes detected.
Exit 2 — comparison complete, changes detected.
Exit 3 — warn-threshold exceeded.

**2. Compare a data view against its previous snapshot:**

```bash
uv run cja_auto_sdr <dv_id> --compare-with-prev --agent-mode > /tmp/diff-report.json
```

**3. Drift detection over a cached snapshot window:**

```bash
uv run cja_auto_sdr --org-report --trending-window 10 --agent-mode > /tmp/drift-report.json
```

`--trending-window 10` means the last 10 cached org-report snapshots, not 10 days.

**4. Parse diff output for breaking changes:**

Inspect these top-level keys in the diff JSON:
- `summary.has_changes` and `summary.total_changes` for the overall decision.
- `metric_diffs` and `dimension_diffs` for item-level additions, removals, and modifications.
- `advisories.findings` for breaking-change rollups. Look for findings with
  `type == "breaking_changes"` or `type == "schema_changes"`.

## Success Criteria

- Exit code 0, 2, or 3 from the diff command means the comparison itself succeeded.
- JSON output is valid and contains a top-level `summary` key.
- If `advisories.summary.by_severity.critical` is absent or `0`, no breaking-change advisory was raised.
- Any critical advisory findings are routed to the appropriate escalation workflow.

## Follow-Up Actions

- **Critical breaking-change advisory:** Block deployment; notify schema owners with the diff report path.
- **Changes without critical advisory:** Log the diff for audit trail; review whether the drift is expected.
- **No changes:** Confirm snapshot is up to date; no action needed.
- **Recurring drift detection:** Pair with `snapshot-manager.md` to capture and compare snapshots on a schedule.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
