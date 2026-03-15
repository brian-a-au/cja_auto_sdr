# Agent Automation Guide

This guide covers how to automate `cja_auto_sdr` in CI/CD pipelines, scheduled jobs, and agent frameworks.

## Table of Contents

1. [Why Automate](#why-automate)
2. [Prerequisites](#prerequisites)
3. [Agent-Friendly CLI Features](#agent-friendly-cli-features)
4. [Configuration for Automation](#configuration-for-automation)
5. [Scheduling Patterns](#scheduling-patterns)
6. [Agent Framework Integration](#agent-framework-integration)
7. [Notification Integration](#notification-integration)
8. [Security Considerations](#security-considerations)
9. [Troubleshooting](#troubleshooting)

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
# JSON to stdout — parse with jq, Python json.loads(), etc.
uv run cja_auto_sdr <dv_id> --format json --output -

# Discovery as JSON
uv run cja_auto_sdr --list-dataviews --format json --output -

# Structured run summary (includes per-DV status, failure codes, output paths)
uv run cja_auto_sdr <dv_id> --format json --run-summary-json -
```

`--output -` implies `--quiet`, so stdout contains only the payload and stderr contains any log output.

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

Agents should use `AGENTS.md` (repo root) as the primary tool contract. It provides:
- Complete command syntax
- Exit code table with agent actions
- Output format guidance
- File convention defaults

### Inline JSON tool definition

If your agent framework requires a tool schema, use this minimal definition:

```json
{
  "name": "cja_auto_sdr",
  "description": "Generate SDR documentation from Adobe CJA data views. Use --format json --output - for machine output.",
  "parameters": {
    "type": "object",
    "properties": {
      "data_view_id": {
        "type": "string",
        "description": "Data view ID (e.g. dv_12345) or exact name"
      },
      "format": {
        "type": "string",
        "enum": ["excel", "csv", "json", "html", "markdown", "all", "reports", "data", "ci"],
        "default": "json"
      },
      "output": {
        "type": "string",
        "description": "Output path. Use '-' for stdout (json/csv only).",
        "default": "-"
      },
      "extra_flags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Additional CLI flags, e.g. ['--dry-run', '--quiet']"
      }
    },
    "required": ["data_view_id"]
  }
}
```

### Orchestrator

`scripts/orchestrator.py` is the recommended starting point for agent-driven batch workflows when you want a thin JSON-emitting wrapper around repeated CLI runs.

```bash
# Discover data views, allow 15 minutes per wrapped CLI command
uv run python scripts/orchestrator.py --discover --timeout 900
```

Unlike the direct CLI, the orchestrator writes both success payloads and its own machine-readable error envelopes to stdout so callers can consume a single JSON stream per invocation. Wrapped child-command stdout/stderr are preserved inside the JSON result objects.

---

## Notification Integration

| Channel       | Mechanism                  | Trigger condition               | Example                                       |
|---------------|----------------------------|---------------------------------|-----------------------------------------------|
| Slack         | Incoming webhook           | Exit code 2 or 3               | `curl -X POST $SLACK_WEBHOOK -d '{"text":"..."}'` |
| Email         | SMTP / `mail` command      | Exit code 1 (error)             | `echo "body" \| mail -s "subject" ops@example.com` |
| PagerDuty     | Events API v2              | Exit code 2 (policy violation)  | `curl -X POST https://events.pagerduty.com/v2/enqueue` |
| Microsoft Teams | Incoming webhook          | Exit code 2 or 3               | `curl -X POST $TEAMS_WEBHOOK -d '{"text":"..."}'` |
| GitHub Issues | `gh issue create`          | Exit code 2 (governance alert)  | `gh issue create --title "SDR drift detected" --body "$(cat summary.json)"` |

Pattern:

```bash
uv run cja_auto_sdr --org-report --fail-on-threshold --duplicate-threshold 5 \
  --format json --output report.json
EXIT=$?

if [ $EXIT -eq 2 ]; then
  PAYLOAD=$(jq -n --arg text "CJA governance threshold exceeded. See report.json." '{text: $text}')
  curl -s -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD"
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
| JSON parse error on `--output -`         | Banner or progress text mixed into stdout      | Ensure `--output -` is used (it implies `--quiet`); do not use `--format console` with stdout    |
| `--validate-config` passes but SDR fails | Data view ID not accessible to service account | Confirm data view ID exists and the service account has the correct CJA product profile access   |
| Exit 2 on governance run without alert   | `--fail-on-threshold` not set                  | Add `--fail-on-threshold` to enable exit code 2 on threshold breach                             |
