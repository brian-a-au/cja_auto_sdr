# Use Cases & Best Practices

Common scenarios and recommended practices for the CJA SDR Generator.

## Use Cases

### Implementation Audit

Quickly understand the breadth and depth of your CJA setup:
- Total metrics and dimensions available
- Component type distribution
- Configuration completeness
- Data quality status

**Best for:** Quarterly reviews, new team member onboarding

```bash
cja_auto_sdr dv_12345 --output-dir ./audits/$(date +%Y%m%d)
```

### Implementation Verification

Ensure your CJA implementation matches planning documents:
- Compare against original SDR
- Validate naming conventions
- Verify all planned metrics exist
- Identify configuration drift

**Best for:** Post-implementation validation, compliance audits

### Data Quality Assurance

Maintain high-quality analytics configuration:
- Identify duplicate components
- Find missing descriptions
- Validate metadata completeness
- Track quality trends over time

**Best for:** Ongoing maintenance, quality improvement initiatives

```bash
# Focus on quality issues only
cja_auto_sdr dv_12345 --max-issues 20
```

### Team Onboarding

Assist new team members in understanding CJA setup:
- Provide complete component reference
- Document available metrics/dimensions
- Share data view configuration
- Explain component relationships

**Best for:** Training, documentation, knowledge transfer

### Change Management

Document configuration before and after changes using the **diff comparison** feature:
- Baseline current configuration with snapshots
- Compare versions over time with automated change detection
- Track component additions, removals, and modifications
- Audit change impact with detailed field-level diffs

**Best for:** Release management, change control processes

```bash
# Save baseline snapshot before change
cja_auto_sdr dv_12345 --snapshot ./baselines/pre-change.json

# After change, compare against baseline
cja_auto_sdr dv_12345 --diff-snapshot ./baselines/pre-change.json

# Or compare two live data views
cja_auto_sdr --diff dv_12345 dv_67890

# Generate HTML report for stakeholders
cja_auto_sdr --diff dv_12345 dv_67890 --format html --output-dir ./reports
```

### Multi-Environment Comparison

Compare configurations across environments using **diff comparison**:
- Directly compare dev, staging, and production data views
- Identify configuration differences with field-level detail
- Ensure consistency across environments before deployments
- Detect environment drift automatically

**Best for:** DevOps, environment management

```bash
# Compare production vs staging directly
cja_auto_sdr --diff "Production Analytics" "Staging Analytics"

# With custom labels in output
cja_auto_sdr --diff dv_12345 dv_67890 --diff-labels "Production" "Staging"

# Show only differences (hide unchanged components)
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only

# Focus on specific change types
cja_auto_sdr --diff dv_12345 dv_67890 --show-only added,removed

# Generate all format reports for review
cja_auto_sdr --diff dv_12345 dv_67890 --format all --output-dir ./env_comparison
```

### Compliance Documentation

Generate audit-ready documentation:
- Complete component inventory
- Metadata completeness tracking
- Data quality reporting
- Timestamped generation logs

**Best for:** SOC2, ISO, internal audit requirements

### Migration Planning

Prepare for migrations or upgrades with **snapshot comparison**:
- Document current state with a baseline snapshot
- Compare before and after migration states
- Validate no unintended changes occurred
- Generate diff reports for migration sign-off

**Best for:** Platform migrations, major version upgrades

```bash
# Before migration: save snapshot
cja_auto_sdr dv_12345 --snapshot ./migrations/pre-migration.json

# Perform migration...

# After migration: compare against baseline
cja_auto_sdr dv_12345 --diff-snapshot ./migrations/pre-migration.json --format html

# Compare two historical snapshots (no API calls needed)
cja_auto_sdr --compare-snapshots ./migrations/pre-migration.json ./migrations/post-migration.json
```

### Data View Drift Detection (CI/CD)

Integrate diff comparison into CI/CD pipelines to catch unexpected changes:
- Automated detection of configuration drift
- Exit codes for pipeline integration (0=no changes, 2=changes found, 3=threshold exceeded)
- PR comments with change summaries
- Fail builds when critical changes exceed thresholds

**Best for:** DevOps, continuous integration, deployment gates

```bash
# Basic CI/CD drift check (exit code 2 if differences found)
cja_auto_sdr --diff dv_12345 dv_67890 --quiet-diff
echo "Exit code: $?"  # 0=identical, 2=different

# Fail build if changes exceed 5%
cja_auto_sdr --diff dv_12345 dv_67890 --warn-threshold 5 --quiet-diff

# Generate PR comment format
cja_auto_sdr --diff dv_12345 dv_67890 --format-pr-comment --diff-output pr-comment.md
gh pr comment --body-file pr-comment.md

# JSON output for programmatic processing
cja_auto_sdr --diff dv_12345 dv_67890 --format json --diff-output changes.json
```

**GitHub Actions Example:**

```yaml
- name: Check for Data View Drift
  run: |
    cja_auto_sdr --diff ${{ secrets.PROD_DV }} ${{ secrets.STAGING_DV }} \
      --warn-threshold 10 --quiet-diff
  continue-on-error: true

- name: Generate Diff Report
  if: failure()
  run: |
    cja_auto_sdr --diff ${{ secrets.PROD_DV }} ${{ secrets.STAGING_DV }} \
      --format-pr-comment --diff-output diff-report.md
```

### Automated Audit Trail

Use **auto-snapshot** to maintain automatic audit trails without manual intervention:
- Automatically save timestamped snapshots during any diff comparison
- Configurable retention policies to manage storage
- Build history of changes over time
- Zero-friction audit compliance

**Best for:** Compliance, audit trails, historical tracking

```bash
# Auto-save snapshots during diff (creates timestamped files)
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot
```

Creates:
- `./snapshots/DataViewName_dv_12345_20260118_143022.json`
- `./snapshots/DataViewName_dv_67890_20260118_143022.json`

```bash
# Custom snapshot directory
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --snapshot-dir ./audit-trail

# With retention policy (keep only last 30 snapshots per data view)
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --keep-last 30

# Works with diff-snapshot too (saves current state automatically)
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --auto-snapshot
```

**Scheduled Audit Trail (cron):**

```bash
# Weekly audit with automatic snapshot retention
0 9 * * 1 cd /path/to/project && cja_auto_sdr \
  --diff dv_12345 dv_67890 \
  --auto-snapshot --keep-last 52 \
  --snapshot-dir ./audit/weekly \
  --format markdown --diff-output ./audit/weekly/latest-diff.md
```

### Quick Comparison Against Previous State

Use `--compare-with-prev` for one-command comparisons against the most recent snapshot:

```bash
# Build up snapshot history over time with auto-snapshot
cja_auto_sdr --diff dv_12345 dv_12345 --auto-snapshot

# Later: compare current state to most recent snapshot
cja_auto_sdr dv_12345 --compare-with-prev

# With custom snapshot directory
cja_auto_sdr dv_12345 --compare-with-prev --snapshot-dir ./audit-trail
```

This eliminates the need to track snapshot filenames—the tool automatically finds and uses the most recent one.

## Best Practices

### Scheduling

Run SDR generation regularly to track changes:

#### Linux/macOS (cron)

```bash
# Edit crontab
crontab -e

# Weekly audit on Monday at 9 AM
0 9 * * 1 cd /path/to/project && cja_auto_sdr dv_12345

# Daily batch at 2 AM
# Note: In crontab, % has special meaning (newline), so it must be escaped with \
0 2 * * * cd /path/to/project && cja_auto_sdr \
  dv_12345 dv_67890 --output-dir /reports/$(date +\%Y\%m\%d) --continue-on-error
```

#### Windows (Task Scheduler)

```powershell
$action = New-ScheduledTaskAction -Execute "uv" `
  -Argument "run cja_auto_sdr dv_12345" `
  -WorkingDirectory "C:\path\to\project"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "CJA SDR Weekly"
```

### Automation Scripts

Create reusable scripts for common operations:

#### generate_production.sh

```bash
#!/bin/bash
cd "$(dirname "$0")/.."
cja_auto_sdr dv_12345 \
  --output-dir ./reports/production \
  --log-level WARNING
```

#### generate_all_environments.sh

```bash
#!/bin/bash
cd "$(dirname "$0")/.."
cja_auto_sdr \
  dv_12345 dv_67890 dv_abcde \
  --output-dir ./reports/$(date +%Y%m%d) \
  --continue-on-error
```

#### Process from File

Create `dataviews.txt`:
```
dv_12345
dv_67890
dv_abcde
dv_11111
dv_22222
```

Then:
```bash
cja_auto_sdr $(cat dataviews.txt) --continue-on-error
```

### Data Quality Management

**Priority handling:**

1. **CRITICAL**: Fix immediately before using reports
2. **HIGH**: Schedule fixes within current sprint
3. **MEDIUM**: Add to backlog, fix opportunistically
4. **LOW**: Address during documentation updates

**Tracking quality over time:**

```bash
# Generate weekly reports with timestamps
cja_auto_sdr dv_12345 \
  --output-dir ./quality_trends/week_$(date +%V)
```

### Version Control

**Files to commit:**
```bash
git add pyproject.toml uv.lock
git commit -m "Update dependencies"
```

**Files to ignore (.gitignore):**
```gitignore
config.json
*.key
*.pem
.venv/
logs/
*.xlsx
```

### Security

- Never commit `config.json` to version control
- Use service accounts for automated runs
- Rotate credentials periodically
- Store private keys in key management systems
- Restrict access to sensitive data views

### Performance Optimization

**Batch processing best practices:**

| Scenario | Workers | Notes |
|----------|---------|-------|
| Shared API (rate limits) | 2 | Conservative approach |
| Balanced (default) | 4 | Good for most cases |
| Dedicated infrastructure | 8+ | Maximum throughput |

**Skip unnecessary processing:**

```bash
# Quick documentation (skip validation)
cja_auto_sdr dv_12345 --skip-validation

# Cache for repeated runs
cja_auto_sdr dv_12345 --enable-cache
```

### CI/CD Integration

#### GitHub Actions - SDR Generation

```yaml
name: Generate SDR
on:
  schedule:
    - cron: '0 9 * * 1'  # Weekly Monday 9 AM
  workflow_dispatch:  # Manual trigger

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync

      - name: Generate SDR
        run: |
          cja_auto_sdr ${{ secrets.DATA_VIEW_ID }} \
            --output-dir ./artifacts
        env:
          ORG_ID: ${{ secrets.ORG_ID }}
          CLIENT_ID: ${{ secrets.CLIENT_ID }}
          SECRET: ${{ secrets.SECRET }}
          SCOPES: ${{ secrets.SCOPES }}

      - uses: actions/upload-artifact@v4
        with:
          name: sdr-reports
          path: ./artifacts/*.xlsx
```

#### GitHub Actions - Diff Comparison with PR Comment

```yaml
name: Data View Drift Check
on:
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM

jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Install dependencies
        run: pip install uv && uv sync

      - name: Check for drift
        id: drift
        run: |
          cja_auto_sdr --diff ${{ secrets.PROD_DV }} ${{ secrets.STAGING_DV }} \
            --warn-threshold 5 \
            --format-pr-comment --diff-output diff-report.md \
            --auto-snapshot --snapshot-dir ./snapshots
          echo "exit_code=$?" >> $GITHUB_OUTPUT
        env:
          ORG_ID: ${{ secrets.ORG_ID }}
          CLIENT_ID: ${{ secrets.CLIENT_ID }}
          SECRET: ${{ secrets.SECRET }}
        continue-on-error: true

      - name: Comment on PR
        if: github.event_name == 'pull_request' && steps.drift.outputs.exit_code != '0'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const body = fs.readFileSync('diff-report.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            });

      - name: Upload snapshots
        uses: actions/upload-artifact@v4
        with:
          name: snapshots
          path: ./snapshots/*.json
```

### Output Organization

**Recommended directory structure:**

```
reports/
├── production/
│   ├── 20260107/
│   │   └── CJA_DataView_Prod_dv_123_SDR.xlsx
│   └── 20260114/
│       └── CJA_DataView_Prod_dv_123_SDR.xlsx
├── staging/
│   └── ...
└── quality_trends/
    ├── week_01/
    ├── week_02/
    └── ...
```

**Organizing by date:**

```bash
cja_auto_sdr dv_12345 \
  --output-dir ./reports/$(date +%Y%m%d)
```

**Organizing by environment:**

```bash
cja_auto_sdr dv_12345 \
  --output-dir ./reports/production/$(date +%Y%m%d)
```

## Target Audiences

| Audience | Key Use Case | Recommended Workflow |
|----------|--------------|---------------------|
| Analytics Teams | Regular SDR documentation | Weekly automated runs |
| DevOps Engineers | CI/CD integration | Pipeline automation |
| Data Governance | Audit trails | Monthly comprehensive reports |
| Consultants | Multi-client management | Batch processing per client |
| Enterprise | Compliance documentation | Scheduled + on-demand |

## See Also

- [CLI Reference](CLI_REFERENCE.md) - All command options
- [Data View Comparison Guide](DIFF_COMPARISON.md) - Diff, snapshots, and CI/CD integration
- [Performance Guide](PERFORMANCE.md) - Optimization tips
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Multi-view processing
- [Data Quality](DATA_QUALITY.md) - Understanding validation
