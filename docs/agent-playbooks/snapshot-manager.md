# Snapshot Manager

## Purpose

Manages the full lifecycle of CJA data view snapshots: creation, listing,
comparison, and pruning. Provides the snapshot infrastructure that other
playbooks (`diff-reviewer.md`, `sdr-auditor.md`) depend on for drift detection
and change tracking.

## When To Use

- Before and after any schema change to capture a before/after pair
- On a scheduled cadence to build a snapshot history for drift detection
- Before running `diff-reviewer.md` (snapshots must exist first)
- When cleaning up stale snapshots to manage storage
- As part of a CI pipeline to record the state of data views at each deployment

## Inputs

**Required (capture):**
- `<dv_id>` — data view ID to snapshot
- `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES` — API credentials (or `--profile <name>`)

**Required (compare):**
- Either two snapshot JSON file paths, or `--compare-with-prev` for the most recent snapshot of one data view

**Optional:**
- `--snapshot <path.json>` — write a snapshot to an explicit file path
- `--snapshot-dir <dir>` — directory scanned by `--compare-with-prev` and `--list-snapshots`
- `--agent-mode` — machine-readable JSON on stdout for compare flows
- `--profile <name>` — named credential profile

## Constraints

- Snapshots are stored locally (or in the configured snapshot directory); they
  are not uploaded to CJA or any remote service.
- `--compare-snapshots` compares snapshot files directly and does not call the API.
- Git-backed snapshots require a git repository at or above the working directory;
  configure with `--git-snapshot` if desired.
- Pruning is irreversible; verify the snapshot list before deleting.
- `--compare-with-prev` requires at least one prior snapshot for the target data view.

## Primary CLI Flows

**1. Capture a named snapshot before a schema change:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> --snapshot ./snapshots/pre-migration.json
echo "Exit: $?"
```

**2. Capture a snapshot after the change:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> --snapshot ./snapshots/post-migration.json
```

**3. List all snapshots for a data view:**

```bash
uv run cja_auto_sdr --list-snapshots <DATA_VIEW_ID> --format json --output -
```

Each entry includes `filename`, `created_at`, and `data_view_id`.

**4. Compare two named snapshots:**

```bash
uv run cja_auto_sdr --compare-snapshots \
  ./snapshots/pre-migration.json \
  ./snapshots/post-migration.json \
  --agent-mode > /tmp/migration-diff.json
```

See `diff-reviewer.md` for full diff workflow.

**5. Compare a data view against its most recent snapshot:**

```bash
uv run cja_auto_sdr <DATA_VIEW_ID> --compare-with-prev --agent-mode > /tmp/incremental-diff.json
```

**6. Capture a timestamped snapshot for scheduled drift tracking:**

```bash
SNAPSHOT_FILE="./snapshots/${DATA_VIEW_ID}_$(date +%Y%m%d).json"
uv run cja_auto_sdr <DATA_VIEW_ID> --snapshot "$SNAPSHOT_FILE"
```

**7. Scheduled drift window query (last 7 cached org-report snapshots):**

```bash
uv run cja_auto_sdr --org-report --trending-window 7 --agent-mode > /tmp/weekly-drift.json
```

## Success Criteria

- Snapshot capture exits 0 and the new filename appears in `--list-snapshots` output.
- Diff between pre/post snapshots exits 0 or 2 and `summary` is present in JSON output.
- Snapshot count grows monotonically over scheduled runs.
- Pruned snapshots no longer appear in `--list-snapshots` output.

## Follow-Up Actions

- **After capturing pre/post snapshots:** Run `diff-reviewer.md` to validate changes.
- **After a clean drift window:** No action needed; log the snapshot filename for audit trail.
- **Drift detected:** Route drift report to `diff-reviewer.md` for full analysis.
- **Snapshot storage growing large:** Prune snapshots older than your retention policy;
  keep at minimum the last baseline and the most recent snapshot per data view.
- **CI integration:** Add snapshot capture as a post-deploy step; compare with
  previous on every run to catch unintended schema changes automatically.

---

> For authoritative CLI contracts, see [AGENTS.md](../../AGENTS.md).
