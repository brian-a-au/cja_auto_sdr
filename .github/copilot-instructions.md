# Copilot instructions for `cja_auto_sdr`

- Read and follow the repository-root `AGENTS.md` before editing. It is the
  authoritative project and tool contract.
- This is a Python 3.14+ CLI managed with `uv`. Install the development
  environment with `uv sync`.
- Preserve the core safety invariant: Adobe Customer Journey Analytics API
  access is read-only. Never add an SDK or HTTP call that creates, updates, or
  deletes Adobe CJA state.
- Output-side integrations are separate from Adobe CJA access. They may write
  only when an existing, explicit user-selected workflow authorizes it, such as
  publishing an SDR to Notion.
- Never expose `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`, access tokens, profile
  contents, sandbox names, or live customer resource data in code, tests, logs,
  fixtures, or pull requests. Use mocks and synthetic fixtures.
- Keep the Adobe SDK boundary inside `src/cja_auto_sdr/api/`; downstream code
  should consume the project's own models rather than leaking `cjapy` objects.
- Preserve documented CLI exit codes, stdout and stderr JSON contracts, output
  conventions, snapshot compatibility, agent-mode behavior, and cross-platform
  behavior.
- Match existing typing, logging, and test patterns. Add or update focused tests
  for behavior changes; do not weaken a security check merely to make CI pass.
- For GitHub Actions changes, grant only the minimum `GITHUB_TOKEN` permissions
  and pin new third-party actions to a full commit SHA with a version comment.

Run the narrowest relevant tests while iterating, then validate a completed
change with:

```bash
uv run pytest -q
uv run ruff check src/ tests/ scripts/ examples/
uv run ruff format --check src/ tests/ scripts/ examples/
uv lock --check
uv run python scripts/check_version_sync.py
uv run python scripts/update_test_counts.py --check
```
