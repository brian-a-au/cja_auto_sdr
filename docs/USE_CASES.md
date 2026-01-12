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
uv run python cja_sdr_generator.py dv_production --output-dir ./audits/$(date +%Y%m%d)
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
uv run python cja_sdr_generator.py dv_12345 --max-issues 20
```

### Team Onboarding

Assist new team members in understanding CJA setup:
- Provide complete component reference
- Document available metrics/dimensions
- Share data view configuration
- Explain component relationships

**Best for:** Training, documentation, knowledge transfer

### Change Management

Document configuration before and after changes:
- Baseline current configuration
- Compare versions over time
- Track component additions/removals
- Audit change impact

**Best for:** Release management, change control processes

```bash
# Before change
uv run python cja_sdr_generator.py dv_12345 --output-dir ./baseline

# After change
uv run python cja_sdr_generator.py dv_12345 --output-dir ./after_change
```

### Multi-Environment Comparison

Compare configurations across environments:
- Generate SDRs for dev, staging, production
- Identify configuration differences
- Ensure consistency across environments
- Plan promotion strategies

**Best for:** DevOps, environment management

```bash
uv run python cja_sdr_generator.py dv_dev dv_staging dv_prod \
  --output-dir ./env_comparison
```

### Compliance Documentation

Generate audit-ready documentation:
- Complete component inventory
- Metadata completeness tracking
- Data quality reporting
- Timestamped generation logs

**Best for:** SOC2, ISO, internal audit requirements

### Migration Planning

Prepare for migrations or upgrades:
- Document current state comprehensively
- Identify components to migrate
- Plan migration sequence
- Validate post-migration configuration

**Best for:** Platform migrations, major version upgrades

## Best Practices

### Scheduling

Run SDR generation regularly to track changes:

#### Linux/macOS (cron)

```bash
# Edit crontab
crontab -e

# Weekly audit on Monday at 9 AM
0 9 * * 1 cd /path/to/project && uv run python cja_sdr_generator.py dv_production

# Daily batch at 2 AM
0 2 * * * cd /path/to/project && uv run python cja_sdr_generator.py \
  dv_prod_1 dv_prod_2 --output-dir /reports/$(date +\%Y\%m\%d) --continue-on-error
```

#### Windows (Task Scheduler)

```powershell
$action = New-ScheduledTaskAction -Execute "uv" `
  -Argument "run python cja_sdr_generator.py dv_production" `
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
uv run python cja_sdr_generator.py dv_production \
  --output-dir ./reports/production \
  --log-level WARNING
```

#### generate_all_environments.sh

```bash
#!/bin/bash
cd "$(dirname "$0")/.."
uv run python cja_sdr_generator.py \
  dv_production dv_staging dv_development \
  --output-dir ./reports/$(date +%Y%m%d) \
  --continue-on-error
```

#### Process from File

Create `dataviews.txt`:
```
dv_production_main
dv_production_eu
dv_production_apac
dv_staging
dv_development
```

Then:
```bash
uv run python cja_sdr_generator.py $(cat dataviews.txt) --continue-on-error
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
uv run python cja_sdr_generator.py dv_12345 \
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
myconfig.json
*.key
*.pem
.venv/
logs/
*.xlsx
```

### Security

- Never commit `myconfig.json` to version control
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
uv run python cja_sdr_generator.py dv_12345 --skip-validation

# Cache for repeated runs
uv run python cja_sdr_generator.py dv_12345 --enable-cache
```

### CI/CD Integration

#### GitHub Actions

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
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.14'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync

      - name: Generate SDR
        run: |
          uv run python cja_sdr_generator.py ${{ secrets.DATA_VIEW_ID }} \
            --output-dir ./artifacts
        env:
          # Store config as secret
          CJA_CONFIG: ${{ secrets.CJA_CONFIG }}

      - uses: actions/upload-artifact@v3
        with:
          name: sdr-reports
          path: ./artifacts/*.xlsx
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
uv run python cja_sdr_generator.py dv_12345 \
  --output-dir ./reports/$(date +%Y%m%d)
```

**Organizing by environment:**

```bash
uv run python cja_sdr_generator.py dv_prod \
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
- [Performance Guide](PERFORMANCE.md) - Optimization tips
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Multi-view processing
- [Data Quality](DATA_QUALITY.md) - Understanding validation
