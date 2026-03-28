# Agent Playbooks

Reusable task guides for common CJA SDR Generator workflows. These playbooks
are repo-native, cross-agent documents — they work with any agent framework
or manual operator.

## Playbooks

| Playbook | Purpose |
|----------|---------|
| [sdr-auditor.md](sdr-auditor.md) | Org-wide governance review with threshold triage |
| [diff-reviewer.md](diff-reviewer.md) | Change review and drift detection |
| [onboarding-guide.md](onboarding-guide.md) | First-run setup and initial SDR generation |
| [quality-monitor.md](quality-monitor.md) | Quality-gate enforcement and reporting |
| [snapshot-manager.md](snapshot-manager.md) | Snapshot lifecycle, comparison, and pruning |

## When to Start With AGENTS.md

Start with [AGENTS.md](../../AGENTS.md) when you need:
- The authoritative CLI contract (flags, exit codes, output formats)
- Setup and authentication instructions
- The complete command reference

Start with a playbook when you need:
- A guided workflow for a specific task
- Step-by-step decision points and branching logic
- Success criteria and follow-up actions

## Important

These playbooks are explicit guides. They are **not** auto-discovered by any
agent platform. Reference them by path when needed.
