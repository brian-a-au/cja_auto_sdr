# Agent Contract Fixtures

Representative JSON payloads for agent-facing output contracts.

These fixtures document the stable structural shape of machine-readable output.
They are intentionally small and exist for contract validation, not as complete
examples.

## Fixtures

| File | Source Command | Contract Surface |
|------|--------------|-----------------|
| `sample_list_dataviews_agent_mode.json` | `--list-dataviews --agent-mode` | `dataViews` collection |
| `sample_org_report_with_advisories.json` | `--org-report --agent-mode` | Top-level `advisories` |
| `sample_diff_with_advisories.json` | `--diff --agent-mode` | Top-level `advisories` |
| `sample_run_summary_with_advisories.json` | `--run-summary-json` | `details.advisories` |

## Stability

These fixtures are tested by `tests/test_agent_contract_samples.py`. Structural
keys are stable; field values are illustrative.
