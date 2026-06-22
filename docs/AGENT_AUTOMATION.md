# Agent Automation Guide

This guide covers how to automate `cja_auto_sdr` in CI/CD pipelines, scheduled jobs, and agent frameworks.

## Table of Contents

1. [Why Automate](#why-automate)
2. [Prerequisites](#prerequisites)
3. [Agent-Friendly CLI Features](#agent-friendly-cli-features)
4. [--agent-mode Flag](#--agent-mode-flag)
5. [Advisories Block](#advisories-block)
6. [Machine-Interface Decision Matrix](#machine-interface-decision-matrix)
7. [Tool Manifests](#tool-manifests)
8. [Configuration for Automation](#configuration-for-automation)
9. [Config Preflight Surfaces](#config-preflight-surfaces)
10. [Exact-ID Guidance](#exact-id-guidance)
11. [Scheduling Patterns](#scheduling-patterns)
12. [Agent Framework Integration](#agent-framework-integration)
13. [Notification Integration](#notification-integration)
14. [Security Considerations](#security-considerations)
15. [Troubleshooting](#troubleshooting)

---

## Why Automate

| Use Case                             | Recommended Cadence          |
|--------------------------------------|------------------------------|
| SDR generation for governance        | Weekly                       |
| Data quality monitoring              | Daily                        |
| Drift detection                      | Daily or on deploy           |
| Multi-org audits                     | Weekly                       |
| Change audit trail                   | Event-driven or nightly      |
| Full SDR regeneration (all views)    | Quarterly                    |
| Cross-org governance review          | Quarterly                    |
| Snapshot pruning & baseline rotation | Quarterly                    |
| Compliance documentation export      | Quarterly or on audit        |

---

## Prerequisites

- **Service account credentials**: An Adobe IMS OAuth server-to-server service account with CJA read access.
- **Auth via environment variables**: Automation must supply credentials through env vars (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`), not `config.json`. See [Configuration for Automation](#configuration-for-automation).
- **Python + uv**: Python 3.14+ and `uv` installed on the runner/agent. Run `uv sync` once after checkout.
- **Adobe API access**: The service account must have the CJA product profile assigned in Adobe Admin Console.

---

## Agent-Friendly CLI Features

### Machine-readable output

```bash
# Discovery JSON to stdout — parse with jq, Python json.loads(), etc.
uv run cja_auto_sdr --list-dataviews --format json --output -

# Org-report JSON to stdout
uv run cja_auto_sdr --org-report --format json --output -

# Structured run summary (includes per-DV status, failure codes, output paths)
uv run cja_auto_sdr <dv_id> --format json --run-summary-json -
```

`--output -` implies `--quiet`, so stdout contains only the payload and stderr contains any log output.
Single-SDR generation currently writes auto-named artifacts under `--output-dir` rather than streaming the SDR payload to stdout.

### Exit codes

Agents should branch on exit codes rather than parsing human-readable output:

| Code | Meaning                          | Recommended action                      |
|------|----------------------------------|-----------------------------------------|
| `0`  | Success                          | Consume output, continue pipeline       |
| `1`  | Error                            | Abort; parse stderr JSON for diagnosis  |
| `2`  | Policy violation                 | Notify; open issue or alert             |
| `3`  | Warn threshold exceeded          | Log warning; optionally escalate        |
| `130`| Interrupted                      | Retry or mark as cancelled              |

### Pre-flight validation

Always run config validation before your first API call in a new environment:

```bash
# Non-interactive config + connectivity check
uv run cja_auto_sdr --validate-config
echo "exit: $?"

# Dry-run without generating output
uv run cja_auto_sdr <dv_id> --dry-run
```

---

## --agent-mode Flag

`--agent-mode` is a convenience preset that configures the CLI for unattended, machine-readable operation.

### What it expands to

`--agent-mode` sets the following defaults when those options are not explicitly provided on the command line:

| Option         | Default applied |
|----------------|-----------------|
| `--format`     | `json`          |
| `--output`     | `-` (stdout)    |
| `--log-format` | `json`          |

If you explicitly pass any of these options, your explicit value takes precedence — `--agent-mode` only fills in options you did not supply.

### Examples by command family

```bash
# SDR generation — preset/logging apply, artifact still lands under output_dir
uv run cja_auto_sdr dv_abc123 --agent-mode --output-dir ./reports

# Batch generation — preset/logging apply, artifacts still land under output_dir
uv run cja_auto_sdr dv_abc123 dv_def456 --agent-mode --continue-on-error --output-dir ./reports

# Org-wide governance report
uv run cja_auto_sdr --org-report --agent-mode

# Org-report with governance gate
uv run cja_auto_sdr --org-report --agent-mode --duplicate-threshold 5 --fail-on-threshold

# Diff — compare two data views
uv run cja_auto_sdr --diff dv_abc123 dv_def456 --agent-mode

# Diff against snapshot
uv run cja_auto_sdr dv_abc123 --diff-snapshot ./snapshots/dv_abc123.json --agent-mode

# Discovery
uv run cja_auto_sdr --list-dataviews --agent-mode

# Config status (machine-readable)
uv run cja_auto_sdr --config-status --config-json --agent-mode
```

### --agent-mode command-family applicability

| Command family                                      | `--agent-mode` supported | Notes |
|-----------------------------------------------------|--------------------------|-------|
| SDR generation (single)                             | Limited                  | Preset applies, but current generation still writes auto-named artifacts under `--output-dir` |
| Batch SDR generation                                | Limited                  | Preset applies, but per-data-view artifacts still land under `--output-dir` |
| Discovery / inspection (`--list-*`, `--describe-dataview`) | Yes             | JSON to stdout for machine-readable flows; prefer exact IDs for unattended inspection |
| Org-report (`--org-report`)                         | Yes                      | JSON to stdout; advisories block included; `--format console --output -` is also valid for human-readable stdout |
| Diff family (`--diff`, `--diff-snapshot`, `--compare-with-prev`, `--compare-snapshots`) | Yes | JSON to stdout; advisories block included |
| Validation / preflight (`--validate-config`, `--config-status`) | Partial        | Use `--config-status --config-json` for JSON state; `--validate-config` is primarily exit-code driven |
| Fast-path flags (`--version`, `--completion`)       | Partial                  | Informational fast paths tolerate `--agent-mode`, but the preset itself is not applied before exit |
| Interactive mode (`--interactive`)                  | No                       | Interactive prompts are not suitable for unattended pipelines |

---

## Advisories Block

Starting in v3.5.0, JSON output for org-report and diff commands includes an `advisories` block with structured findings and a `recommended_actions` registry. Agents should read `advisories.recommended_actions` to determine follow-up steps.

### Advisories block structure

```json
{
  "advisories": {
    "advisories_version": "1.0",
    "severity": "critical",
    "summary": {
      "total_findings": 2,
      "by_severity": {"critical": 1, "warning": 1}
    },
    "findings": [
      {
        "type": "governance_threshold_breach",
        "severity": "critical",
        "message": "One or more governance thresholds have been exceeded.",
        "details": { "count": 3, "violations": [...] },
        "recommended_actions": ["review_governance_thresholds", "remediate_threshold_breach"]
      }
    ],
    "recommended_actions": ["review_governance_thresholds", "remediate_threshold_breach"]
  }
}
```

The top-level `recommended_actions` list is a deduplicated union of all finding-level actions, ordered by first appearance.

### Org-report recommended_actions registry

| Action token                    | Triggered by finding type          | Meaning                                                      |
|---------------------------------|------------------------------------|--------------------------------------------------------------|
| `review_overlap_pairs`          | `high_overlap`                     | Inspect the flagged data view pairs for intentional overlap  |
| `verify_intentional_duplicates` | `high_overlap`                     | Confirm duplicates are deliberate (e.g. regional variants)   |
| `review_isolated_views`         | `isolated_review`                  | Examine data views with many isolated components             |
| `add_descriptions`              | `metadata_hygiene`                 | Add missing descriptions to flagged data views               |
| `review_stale_views`            | `metadata_hygiene`                 | Review stale data views and confirm they are still needed    |
| `review_governance_thresholds`  | `governance_threshold_breach`      | Review which thresholds are configured and why they fired    |
| `remediate_threshold_breach`    | `governance_threshold_breach`      | Take corrective action on breached governance thresholds     |
| `investigate_fetch_failures`    | `fetch_failures`                   | Diagnose why specific data views could not be fetched        |
| `review_drift_activity`         | `drift_activity`                   | Inspect which data views are drifting and by how much        |
| `compare_recent_reports`        | `drift_activity`                   | Run `--compare-org-report` against a recent baseline         |

`metadata_hygiene` can emit one or both of `add_descriptions` and `review_stale_views`, depending on which underlying recommendations are present.

### Diff recommended_actions registry

| Action token                    | Triggered by finding type | Meaning                                                         |
|---------------------------------|---------------------------|-----------------------------------------------------------------|
| `review_breaking_changes`       | `breaking_changes`        | Inspect removed components before merging or deploying          |
| `update_downstream_dependencies`| `breaking_changes`        | Update any analytics or BI tools that reference removed fields  |
| `review_schema_changes`         | `schema_changes`          | Review modified component definitions for unintended changes    |
| `validate_mappings`             | `schema_changes`          | Re-validate field mappings in downstream consumers              |
| `acknowledge_additive_change`   | `additions_only`          | Confirm additions are expected; no breaking changes detected    |

### Severity levels

| Severity   | Meaning                                             |
|------------|-----------------------------------------------------|
| `critical` | Immediate action required; may block CI gates       |
| `warning`  | Review recommended; does not fail unless gated      |
| `info`     | Informational; no action strictly required          |

---

## Machine-Interface Decision Matrix

| Need                                              | Use                                                 |
|---------------------------------------------------|-----------------------------------------------------|
| Direct JSON payload from CLI                      | `--agent-mode` or `--format json --output -`        |
| Structured run metadata (exit code, counts, paths)| `--run-summary-json <file>` (use `-` for stdout)    |
| Batched SDR/discovery from Python                 | `scripts/orchestrator.py`                           |
| LLM agent tool calling                            | `tools/*.json` manifests                            |
| Config validation before pipeline step            | `--validate-config` or `--config-status --config-json` |
| Structured advisories on org / diff results       | `advisories` block in JSON output (`--agent-mode`)  |

---

## Tool Manifests

`tools/` contains OpenAI-style JSON function definitions (tool manifests) for integrating `cja_auto_sdr` into agent frameworks (OpenAI function calling, Anthropic tool use, LangChain, etc.). These manifests are the **authoritative tool-schema surface** for agent integration.

| File                      | Tool name             | Purpose                                      |
|---------------------------|-----------------------|----------------------------------------------|
| `tools/cja_sdr_generate.json`   | `cja_sdr_generate`  | Single data view SDR generation            |
| `tools/cja_sdr_discover.json`   | `cja_sdr_discover`  | Discovery and resource inspection          |
| `tools/cja_sdr_config.json`     | `cja_sdr_config`    | Config preflight and status checks         |
| `tools/cja_sdr_diff.json`       | `cja_sdr_diff`      | Snapshot comparison and drift detection    |
| `tools/cja_sdr_governance.json` | `cja_sdr_governance`| Org-wide governance reporting              |

See `tools/README.md` for full parameter documentation, command-family applicability notes, and example tool-calling sequences.

> **Note:** Any inline tool JSON shown elsewhere in this documentation is illustrative only. Always use the manifests in `tools/` as the authoritative schema source.

---

## Configuration for Automation

### Environment variable setup

```bash
export ORG_ID="XXXXXXXX@AdobeOrg"
export CLIENT_ID="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export SECRET="p8e-XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
export SCOPES="openid,AdobeID,read_organizations,additional_info.projectedProductContext"
```

### Secrets managers

Inject credentials from your secrets manager before invoking the tool:

```bash
# AWS Secrets Manager
export SECRET=$(aws secretsmanager get-secret-value --secret-id cja/prod/secret --query SecretString --output text)

# HashiCorp Vault
export SECRET=$(vault kv get -field=secret secret/cja/prod)

# GitHub Actions — use environment secrets (see Scheduling Patterns)
```

### Rules

- Never hardcode credentials in scripts, config files, or source control.
- Never commit `config.json` containing live credentials.
- Use short-lived tokens or rotate secrets on a defined schedule.
- Scope service accounts to read-only CJA access.

---

## Config Preflight Surfaces

Two CLI surfaces support pre-flight validation in automated pipelines:

### --validate-config

Performs a lightweight credential resolution and API ping without generating any SDR output. Use this as the first step in any pipeline to catch auth and connectivity issues early.

```bash
uv run cja_auto_sdr --validate-config
# Exit 0 → credentials resolved and API reachable
# Exit 1 → configuration or connectivity error (parse stderr JSON)
```

### --config-status --config-json

Emits the effective resolved configuration as a JSON object. Useful for audit logging and pipeline diagnostics. Credentials are masked in the output.

```bash
uv run cja_auto_sdr --config-status --config-json
# stdout: JSON object with resolved profile, org_id (masked), workers, cache settings, etc.
```

Combine with `--agent-mode` for consistent JSON log output:

```bash
uv run cja_auto_sdr --config-status --config-json --agent-mode
```

Recommended preflight sequence for automated pipelines:

```bash
# 1. Validate credentials and connectivity
uv run cja_auto_sdr --validate-config || { echo "Config validation failed"; exit 1; }

# 2. Log effective config for audit trail
uv run cja_auto_sdr --config-status --config-json >> pipeline_audit.jsonl

# 3. Proceed with primary command
uv run cja_auto_sdr dv_abc123 --agent-mode --run-summary-json run_summary.json
```

---

## Exact-ID Guidance

Always use **exact data view IDs** (e.g. `dv_abc123xyz`) in unattended automation, never display names.

- Display names are not guaranteed to be unique across an org. Two data views can share the same name in different connections.
- Name-based resolution requires an extra list API call and may match the wrong data view silently.
- IDs beginning with `dv_` are stable CJA identifiers that do not change when a data view is renamed.

To enumerate available data view IDs before an automated run:

```bash
uv run cja_auto_sdr --list-dataviews --format json --output - | jq '[.[] | {id, name}]'
```

Or use the `cja_sdr_discover` tool manifest with `command: "list_dataviews"` in agent frameworks.

---

## Scheduling Patterns

### Shell script (cron / systemd timer)

See `examples/automation/weekly_sdr.sh` for a reference weekly SDR generation script covering:
- Env var injection from a secrets file
- Drift detection with `--diff-snapshot`
- Exit code branching
- Slack notification on policy violation (exit 2)

### GitHub Actions

See `examples/github-actions/cja-sdr-audit.yml` for a reference workflow covering:
- Scheduled weekly trigger
- Credential injection from repository secrets
- Artifact upload of generated SDR files
- Snapshot commits when the job has `contents: write`

### Multi-org orchestration

See `scripts/orchestrator.py` for a Python orchestration script that:
- Forwards `--profile` / `--config-file` into wrapped CLI calls
- Uses explicit IDs, `DATA_VIEWS`, or `--discover` for data view selection
- Anchors `uv` project resolution to this repository without changing caller-relative file semantics
- Emits a consolidated JSON report with aggregated exit codes
- Uses a per-command timeout of 300 seconds by default; pass `--timeout SECONDS` for larger orgs or slower environments

---

## Agent Framework Integration

### Tool manifests vs. orchestrator

The repo exposes two distinct automation surfaces:

| Surface | Best for |
|---------|----------|
| `tools/*.json` manifests | LLM agent frameworks (OpenAI function calling, Anthropic tool use, LangChain) |
| `scripts/orchestrator.py` | Python-native batch pipelines, CI scripts, subprocess orchestration |

`scripts/orchestrator.py` is currently strongest for batched SDR generation and discovery workflows. It is not the primary integration point for org-report and diff-family flows in agent frameworks — use the `tools/cja_sdr_governance.json` and `tools/cja_sdr_diff.json` manifests for those.

### Root AGENTS.md / CLAUDE.md vs. docs/agent-playbooks/

| Document | Purpose |
|----------|---------|
| `AGENTS.md` (repo root) | Primary tool contract: complete command syntax, exit codes, output format guidance, file conventions. Start here for any agent integration. |
| `CLAUDE.md` (repo root) | Developer instructions for Claude Code: project architecture, test conventions, version bump checklist. Not an agent tool contract. |
| `docs/agent-playbooks/` | Scenario-specific playbooks (SDR auditor, diff reviewer, quality monitor, snapshot manager, onboarding guide). Use these for task-scoped agent configuration. |
| `docs/AGENT_AUTOMATION.md` | Scheduling patterns, agent framework integration, advisories, security. The document you are reading. |

For any new agent integration, the recommended reading order is:
1. `AGENTS.md` — command contract and exit codes
2. `tools/README.md` — tool manifests and parameter reference
3. `docs/agent-playbooks/<scenario>.md` — task-specific guidance
4. `docs/AGENT_AUTOMATION.md` — scheduling, security, advisories

### Structured run summary

`--run-summary-json` writes a JSON file after each command that includes exit code, duration, component counts, and advisory rollup. For single-SDR generation under `--agent-mode`, use a file path because the preset already routes primary output to stdout. Use `-` only when the command is not already emitting its main payload on stdout.

```bash
uv run cja_auto_sdr dv_abc123 --agent-mode --run-summary-json run_summary.json
```

The run summary includes an `advisories` rollup key when advisories are present (org-report and diff commands).

---

## Notification Integration

| Channel       | Mechanism                  | Trigger condition               | Example                                       |
|---------------|----------------------------|---------------------------------|-----------------------------------------------|
| Slack         | Incoming webhook           | Exit code 2 or 3               | `curl -X POST $SLACK_WEBHOOK -d '{"text":"..."}'` |
| Email         | SMTP / `mail` command      | Exit code 1 (error)             | `echo "body" \| mail -s "subject" ops@example.com` |
| PagerDuty     | Events API v2              | Exit code 2 (policy violation)  | `curl -X POST https://events.pagerduty.com/v2/enqueue` |
| Microsoft Teams | Incoming webhook          | Exit code 2 or 3               | `curl -X POST $TEAMS_WEBHOOK -d '{"text":"..."}'` |
| GitHub Issues | `gh issue create`          | Exit code 2 (governance alert)  | `gh issue create --title "SDR drift detected" --body "$(cat summary.json)"` |
| Notion        | `--format notion` or `--push-to-notion` | Every run or post-pipeline | `cja_auto_sdr dv_12345 --format notion` |

### Publishing to Notion

Notion is supported as a first-class output destination for SDR generation and org-report catalog publishing. Install the optional extra and set the required env vars:

```bash
uv pip install 'cja-auto-sdr[notion]'
export NOTION_TOKEN=secret_...
export NOTION_PARENT_PAGE_ID=<page-id>
```

```bash
# Two-step CI pattern: generate JSON, then push to Notion separately
uv run cja_auto_sdr dv_12345 --format json --output-dir ./artifacts
uv run cja_auto_sdr --push-to-notion ./artifacts/dv_12345_sdr.json

# Single-step: generate detail page and publish
uv run cja_auto_sdr dv_12345 --format notion
```

Page IDs are tracked in `.notion_pages.json` so re-runs update the existing page rather than accumulating duplicates. Use `--notion-force-new` to override.

**SDR Registry database pattern (v3.8.0):**

The registry database maintains one row per data view in a "CJA SDR Registry" Notion database, keyed by Data View ID. It has 14 properties covering counts, data quality, timezone, currency, and a link to the detail page.

```bash
# One-time: create the registry database on your first publish
# (--notion-create-database needs a data view + --format notion; it is not standalone)
uv run cja_auto_sdr dv_12345 --format notion --notion-create-database
# Prints the new database ID  ← save this
# Optional custom title: add --notion-database-title "My Registry" (or set NOTION_DATABASE_TITLE)

export NOTION_DATABASE_ID=<id-from-above>

# Per-data-view: publish detail page + upsert complete registry row
uv run cja_auto_sdr dv_12345 --format notion

# Batch: multiple data views with complete rows
uv run cja_auto_sdr --batch dv_12345 dv_67890 dv_abcde --format notion
```

**Org-report catalog pattern (v3.8.0 — lightweight):**

`--org-report --format notion` writes a lightweight catalog row per data view from the org report summary. This is fast (serial, no extra API calls) but only fills Name, Data View ID, Metrics Count, Dimensions Count, owner/dates, and an SDR Page link where a detail page already exists. Segments, Calculated Metrics, Derived Fields counts, and Data Quality are not populated.

```bash
# Lightweight catalog from org report (fast, counts only)
uv run cja_auto_sdr --org-report --format notion

# Follow up with batch for complete rows on key data views
uv run cja_auto_sdr --batch dv_12345 dv_67890 --format notion
```

Use `--org-report --format notion` for a quick high-level view; use `--batch --format notion` when you need complete rows with all 14 properties.

**Orphan page pruning pattern (v3.9.0):**

Each time `--notion-force-new` forces a new page, the superseded page ID is recorded in `.notion_pages.json`. Orphaned pages accumulate in Notion until pruned. Add this maintenance step to your periodic pipeline:

```bash
# Preview what would be archived (no changes made)
uv run cja_auto_sdr --notion-prune-orphans --dry-run --output-dir ./artifacts

# Archive orphaned pages (moved to Notion trash — recoverable)
uv run cja_auto_sdr --notion-prune-orphans --output-dir ./artifacts
```

`--notion-prune-orphans` requires only `NOTION_TOKEN` (no CJA API credentials needed). It is a standalone maintenance command and is rejected when combined with `--org-report`, `--diff`, `--batch`, `--watch`, or `--push-to-notion`.

> **Limitation:** Only pages orphaned by `--notion-force-new` from v3.9.0 onward are tracked. Pages left behind by earlier runs are not catalogued and are unaffected by pruning.

**Registry schema maintenance (v3.10.0):**

Over time, schema additions may leave an existing registry database missing new properties. Two standalone commands help you inspect and repair the database schema without touching any rows or existing properties:

```bash
# Print the canonical CJA SDR Registry schema and exit (no credentials needed)
cja_auto_sdr --notion-print-database-schema

# Preview what would be added (no changes made)
cja_auto_sdr --notion-repair-database --dry-run --notion-database-id <id>

# Apply missing properties to the database
cja_auto_sdr --notion-repair-database --notion-database-id <id>
```

`--notion-repair-database` is add-only: it adds missing properties and reports type conflicts, but never changes or removes existing properties or rows. It requires only `NOTION_TOKEN` and a database id (via `--notion-database-id` or the `NOTION_DATABASE_ID` env var). Combine with `--dry-run` to preview changes before applying. It is a standalone maintenance command and is rejected when combined with other commands.

`--notion-print-database-schema` prints the canonical schema and exits immediately — no credentials or network access required.

Pattern:

```bash
uv run cja_auto_sdr --org-report --agent-mode --fail-on-threshold --duplicate-threshold 5 \
  --output report.json
EXIT=$?

if [ $EXIT -eq 2 ]; then
  PAYLOAD=$(jq -n --arg text "CJA governance threshold exceeded. See report.json." '{text: $text}')
  curl -s -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD"
fi
```

### Reacting to advisories

For richer notifications, read `recommended_actions` from the advisories block:

```bash
ACTIONS=$(jq -r '.advisories.recommended_actions[]' report.json 2>/dev/null || echo "")

if echo "$ACTIONS" | grep -q "remediate_threshold_breach"; then
  # Page on-call for critical threshold breach
  curl -s -X POST https://events.pagerduty.com/v2/enqueue \
    -H 'Authorization: Token token='"$PD_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"routing_key":"'"$PD_KEY"'","event_action":"trigger","payload":{"summary":"CJA governance threshold breach","severity":"critical","source":"cja_auto_sdr"}}'
fi
```

---

## Security Considerations

- **Env vars over files**: Supply credentials through environment variables, not `config.json`. Env vars are process-scoped and do not persist to disk.
- **Secrets managers**: Prefer AWS Secrets Manager, HashiCorp Vault, or your platform's native secret store over `.env` files in CI runners.
- **Service accounts**: Create a dedicated Adobe IMS service account for automation. Do not reuse personal developer credentials.
- **Secret rotation**: Rotate `CLIENT_ID` and `SECRET` on a defined schedule (quarterly minimum). Update secrets manager entries before old credentials expire.
- **Read-only scoping**: Scope the service account to the minimum required product profiles. CJA read access is sufficient; do not grant admin or write privileges.
- **Audit logging**: Enable structured logging with `--log-format json --log-level INFO` and ship logs to your SIEM or log aggregator for audit trail purposes.
- **No secrets in logs**: The tool masks credentials in `--config-status` output, but never pass raw `SECRET` values as positional arguments or embed them in log messages in your wrapper scripts.

---

## Troubleshooting

| Symptom                                  | Likely Cause                                   | Fix                                                                                              |
|------------------------------------------|------------------------------------------------|--------------------------------------------------------------------------------------------------|
| Exit 1 with `error_type: configuration_error` | Missing or expired credentials             | Verify `ORG_ID`, `CLIENT_ID`, `SECRET` env vars are set and the secret has not expired           |
| Exit 1 with `error_type: api_error`      | API connectivity failure or rate limit         | Check network access to Adobe IMS/CJA endpoints; implement retry with `--max-retries` and `--retry-max-delay` |
| Stale snapshot comparison misses changes | Snapshot file is too old or wrong data view    | Re-run `uv run cja_auto_sdr <dv_id> --snapshot <file>` to refresh; check `--snapshot-dir` path  |
| Git commit step fails in CI              | Missing git identity on runner                 | Set `git config user.email` and `git config user.name` in the workflow before any git steps      |
| Rate limiting (429 errors)               | Too many concurrent requests                   | Reduce `--workers` count; increase `--retry-base-delay`; use `--org-report --use-cache`          |
| JSON parse error on `--output -`         | Banner or progress text mixed into stdout      | Ensure `--format json --output -` is used for machine-readable stdout. Org-report `--format console --output -` is valid, but it is human-readable rather than JSON |
| `--validate-config` passes but SDR fails | Data view ID not accessible to service account | Confirm data view ID exists and the service account has the correct CJA product profile access   |
| Exit 2 on governance run without alert   | `--fail-on-threshold` not set                  | Add `--fail-on-threshold` to enable exit code 2 on threshold breach                             |
| `advisories` block absent from JSON output | Command family or format does not emit advisories | Advisories are emitted for org-report and diff commands with `--format json`; use `--agent-mode` |
