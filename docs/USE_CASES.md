# Use Cases & Best Practices

Common scenarios and recommended practices for the CJA SDR Generator.

## Table of Contents

- [Use Cases](#use-cases)
  - [Implementation Audit](#implementation-audit)
  - [Implementation Verification](#implementation-verification)
  - [Data Quality Assurance](#data-quality-assurance)
  - [Team Onboarding](#team-onboarding)
  - [Change Management](#change-management)
  - [Multi-Environment Comparison](#multi-environment-comparison)
  - [Compliance Documentation](#compliance-documentation)
  - [Migration Planning](#migration-planning)
  - [Connection & Dataset Discovery](#connection--dataset-discovery)
  - [Discovery Inspection](#discovery-inspection)
  - [Data View Drift Detection (CI/CD)](#data-view-drift-detection-cicd)
  - [Automated Audit Trail](#automated-audit-trail)
  - [Multi-Organization Management](#multi-organization-management)
  - [Quick Comparison Against Previous State](#quick-comparison-against-previous-state)
  - [Component Inventory & Governance](#component-inventory--governance)
  - [Complexity Analysis & Technical Debt](#complexity-analysis--technical-debt)
  - [Dependency Mapping](#dependency-mapping)
  - [Org-Wide Governance & Standardization](#org-wide-governance--standardization)
  - [Data View Consolidation Planning](#data-view-consolidation-planning)
  - [Cross-Team Component Sharing](#cross-team-component-sharing)
- [Best Practices](#best-practices)
  - [Scheduling](#scheduling)
  - [Automation Scripts](#automation-scripts)
  - [Data Quality Management](#data-quality-management)
  - [Version Control](#version-control)
  - [Security](#security)
  - [Performance Optimization](#performance-optimization)
  - [CI/CD Integration](#cicd-integration)
  - [Output Organization](#output-organization)
- [Target Audiences](#target-audiences)
- [See Also](#see-also)

---

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

### Connection & Dataset Discovery

Understand your CJA infrastructure before generating SDRs:
- Inventory all connections and their backing datasets
- Map which data views are connected to which datasets
- Identify shared connections across multiple data views
- Export connection/dataset inventories for governance documentation

**Best for:** New team members, infrastructure audits, migration planning, governance reviews

```bash
# List all connections with their datasets
cja_auto_sdr --list-connections

# Export connection inventory as CSV for spreadsheet analysis
cja_auto_sdr --list-connections --format csv --output connections.csv

# List all data views with their backing connections and datasets
cja_auto_sdr --list-datasets

# Export dataset mapping as JSON for programmatic use
cja_auto_sdr --list-datasets --format json --output datasets.json

# Discover connections across multiple organizations
for profile in client-a client-b; do
  echo "=== $profile ==="
  cja_auto_sdr --profile "$profile" --list-connections --format json \
    --output "./inventory/${profile}_connections.json"
done
```

> **Note:** Full connection details (names, owners, dataset names) require the API service account to be a CJA Product Admin. Without admin privileges, the tool shows connection IDs derived from data views. See [Troubleshooting](TROUBLESHOOTING.md#connections-api-returns-empty-results) for setup instructions.

### Discovery Inspection

Drill into a single data view's components without generating a full SDR:
- Quick-check what metrics, dimensions, segments, or calculated metrics exist
- Pre-SDR exploration to verify a data view has the expected components
- Filter and sort component lists to find specific items
- Export component inventories for stakeholder review or automation

**Best for:** Pre-SDR exploration, quick component audits, CI validation, data view onboarding

```bash
# Describe a data view — metadata and component counts at a glance
cja_auto_sdr --describe-dataview dv_abc123

# Use a data view name instead of an ID
cja_auto_sdr --describe-dataview "Production Web Data"

# List all metrics, filtered to revenue-related
cja_auto_sdr --list-metrics dv_abc123 --filter revenue

# Export dimensions as CSV for spreadsheet review
cja_auto_sdr --list-dimensions dv_abc123 --format csv --output dims.csv

# List segments with owner and governance info
cja_auto_sdr --list-segments dv_abc123

# Export calculated metrics as JSON for programmatic use
cja_auto_sdr --list-calculated-metrics dv_abc123 --format json --output calcs.json

# Combine filter, sort, and limit
cja_auto_sdr --list-dimensions dv_abc123 --filter "evar|prop" --sort name --limit 20

# Exclude test components
cja_auto_sdr --list-metrics dv_abc123 --exclude "test|debug"

# Fuzzy name matching across organizations
cja_auto_sdr --list-metrics "Prod Web" --name-match fuzzy --profile client-a
```

> **Note:** All five inspection commands support `--format console/json/csv`, `--output`, `--profile`, and `--name-match`. The four list commands also support `--filter`, `--exclude`, `--sort`, and `--limit`. See [CLI Reference](CLI_REFERENCE.md#discovery-inspection) for full details.

### Data View Drift Detection (CI/CD)

Integrate diff comparison into CI/CD pipelines to catch unexpected changes:
- Automated detection of configuration drift
- Exit codes for pipeline integration (0=pass, 2=policy threshold exceeded, 3=diff warning threshold exceeded)
- PR comments with change summaries
- Fail builds when critical changes exceed thresholds

**Best for:** DevOps, continuous integration, deployment gates

```bash
# Basic CI/CD drift check (exit code 2 if differences found)
cja_auto_sdr --diff dv_12345 dv_67890 --quiet-diff
echo "Exit code: $?"  # 0=identical, 2=different, 3=warn-threshold exceeded

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

### Multi-Organization Management

Manage SDR documentation across multiple Adobe Organizations without manual config file switching:

**Best for:** Agencies, consultants, enterprises with regional orgs, multi-brand companies

```bash
# One-time setup: Create profiles for each organization
cja_auto_sdr --profile-add client-a
cja_auto_sdr --profile-add client-b
cja_auto_sdr --profile-add internal

# List all profiles
cja_auto_sdr --profile-list

# Generate SDR for different organizations
cja_auto_sdr --profile client-a "Production Analytics" --format excel
cja_auto_sdr --profile client-b "Main Data View" --format excel

# Test profile connectivity before use
cja_auto_sdr --profile-test client-a

# Set default profile for a session
export CJA_PROFILE=client-a
cja_auto_sdr --list-dataviews  # Uses client-a credentials
```

**Batch processing across organizations:**

```bash
#!/bin/bash
# generate_all_clients.sh

for profile in client-a client-b client-c; do
  echo "Processing $profile..."
  cja_auto_sdr --profile "$profile" --list-dataviews --format json \
    | jq -r '.dataViews[].id' \
    | xargs -I {} cja_auto_sdr --profile "$profile" {} \
        --output-dir "./reports/$profile/$(date +%Y%m%d)"
done
```

See the [Profile Management](CONFIGURATION.md#profile-management) section in the Configuration Guide for full documentation.

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

### Component Inventory & Governance

Document and audit all CJA components beyond the standard SDR using **inventory features**:
- Segments (filters) with complexity scores and definition summaries
- Derived fields with logic breakdowns and schema references
- Calculated metrics with formula analysis and metric dependencies

**Best for:** Component governance, documentation audits, technical reviews

```bash
# Generate full SDR with all component inventories (v3.1.0 shorthand)
cja_auto_sdr dv_12345 --include-all-inventory

# Equivalent longhand
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived

# Quick inventory statistics without full output
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary

# Generate inventory-only output (no standard SDR sheets)
cja_auto_sdr dv_12345 --include-all-inventory --inventory-only

# Output in multiple formats for different stakeholders
cja_auto_sdr dv_12345 --include-all-inventory -f all

# JSON output for programmatic analysis
cja_auto_sdr dv_12345 --include-segments -f json -o segments_inventory.json
```

**Governance Audit Examples:**

```bash
# Quick audit summary (v3.1.0)
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary

# Find all unapproved segments
cja_auto_sdr dv_12345 --include-segments -f json | \
  jq '.segments.segments[] | select(.approved == false) | .segment_name'

# List high-complexity calculated metrics (score >= 75)
cja_auto_sdr dv_12345 --include-calculated -f json | \
  jq '.calculated_metrics.metrics[] | select(.complexity_score >= 75)'

# Export all inventories for external review
cja_auto_sdr dv_12345 --include-all-inventory --inventory-only -f csv
```

### Complexity Analysis & Technical Debt

Identify complex components that may need refactoring or documentation:
- Complexity scores (0-100) highlight components needing attention
- Definition summaries provide human-readable logic descriptions
- Function usage tracking shows which operations are used
- Completion warnings highlight high-complexity components (v3.1.0)

**Best for:** Technical debt assessment, refactoring prioritization, code review

```bash
# Quick complexity check (v3.1.0 - shows high-complexity counts)
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary

# Generate complexity report for all component types
cja_auto_sdr dv_12345 --include-all-inventory -f json -o complexity_report.json

# Analyze complexity in JSON output
cat complexity_report.json | jq '
  .segments.segments
  | sort_by(-.complexity_score)
  | .[0:10]
  | .[] | {name: .segment_name, score: .complexity_score}
'
```

**v3.1.0 Complexity Warnings:** When SDR generation completes with inventory options enabled, you'll see warnings about high-complexity components (score ≥ 75):

```
⚠ High complexity components detected:
  - Segments: 3 with complexity ≥ 75
  - Calculated Metrics: 2 with complexity ≥ 75
  Review the inventory sheets for details.
```

**Complexity Score Interpretation:**

| Score | Level | Action |
|-------|-------|--------|
| 0-25 | Low | No action needed |
| 26-50 | Moderate | Document if not already |
| 51-75 | Elevated | Review and consider simplification |
| 76-100 | High | Prioritize for refactoring or detailed documentation |

### Dependency Mapping

Track how components reference each other:
- Segments: dimension references, metric references, nested segment references
- Calculated metrics: metric references, segment filter references
- Derived fields: schema field references, lookup references

**Best for:** Impact analysis, deprecation planning, component cleanup

```bash
# Generate all inventory data for dependency analysis
cja_auto_sdr dv_12345 --include-all-inventory -f json -o dependencies.json

# Find segments using a specific dimension
cja_auto_sdr dv_12345 --include-segments -f json | \
  jq '.segments.segments[] | select(.dimension_references | contains(["pageName"]))'

# Find calculated metrics referencing a specific metric
cja_auto_sdr dv_12345 --include-calculated -f json | \
  jq '.calculated_metrics.metrics[] | select(.metric_references | contains(["revenue"]))'

# Find all components with segment dependencies
cja_auto_sdr dv_12345 --include-calculated -f json | \
  jq '.calculated_metrics.metrics[] | select(.segment_references | length > 0)'
```

**Dependency Analysis Workflow:**

```bash
#!/bin/bash
# dependency_analysis.sh - Find all dependencies for a component

COMPONENT=$1
DATA_VIEW=$2

echo "=== Analyzing dependencies for: $COMPONENT ==="

# Check segments
echo -e "\n--- Segments referencing $COMPONENT ---"
cja_auto_sdr $DATA_VIEW --include-segments -f json 2>/dev/null | \
  jq --arg comp "$COMPONENT" '
    .segments.segments[]
    | select(
        (.dimension_references | contains([$comp])) or
        (.metric_references | contains([$comp]))
      )
    | .segment_name
  '

# Check calculated metrics
echo -e "\n--- Calculated Metrics referencing $COMPONENT ---"
cja_auto_sdr $DATA_VIEW --include-calculated -f json 2>/dev/null | \
  jq --arg comp "$COMPONENT" '
    .calculated_metrics.metrics[]
    | select(.metric_references | contains([$comp]))
    | .metric_name
  '
```

### Org-Wide Governance & Standardization

Analyze component usage patterns across all data views in your organization using **org-wide analysis**:
- Identify **core components** used organization-wide (50%+ of data views)
- Detect **duplicate data views** with high Jaccard similarity
- Find **standardization opportunities** (components in 70-99% of DVs)
- Generate **governance recommendations** based on usage patterns

**Best for:** Analytics governance, org audits, standardization initiatives

```bash
# Basic org-wide analysis (console output)
cja_auto_sdr --org-report

# Filter to specific data views
cja_auto_sdr --org-report --filter "Prod.*" --exclude "Test|Sandbox"

# Export governance report to Excel
cja_auto_sdr --org-report --format excel --output-dir ./governance

# Include component names for readability
cja_auto_sdr --org-report --include-names --format excel

# Custom thresholds for classification
cja_auto_sdr --org-report --core-threshold 0.7 --overlap-threshold 0.9

# JSON output for programmatic analysis
cja_auto_sdr --org-report --format json --output org_analysis.json
```

**Understanding Distribution Buckets:**

| Bucket | Criteria | Interpretation |
|--------|----------|----------------|
| **Core** | 50%+ of DVs | Foundation components, org-wide standards |
| **Common** | 25-49% of DVs | Shared across teams, potential standards |
| **Limited** | 2+ DVs, < 25% | Team-specific or use-case specific |
| **Isolated** | 1 DV only | Unique to single data view, review for orphans |

**Governance Audit Workflow:**

```bash
#!/bin/bash
# org_governance_audit.sh - Generate comprehensive governance report

OUTPUT_DIR="./governance/$(date +%Y%m%d)"
mkdir -p "$OUTPUT_DIR"

# Full report in all formats
cja_auto_sdr --org-report \
  --include-names \
  --format all \
  --output-dir "$OUTPUT_DIR"

echo "Governance report saved to: $OUTPUT_DIR"

# Extract high-priority recommendations
cja_auto_sdr --org-report --format json --output - | \
  jq '.recommendations[] | select(.severity == "high")'
```

### Data View Consolidation Planning

Use org-wide analysis to plan data view consolidation:
- Identify near-duplicate data views (90%+ similarity)
- Find candidates for merging based on component overlap
- Validate prod/staging parity before deployments

**Best for:** Platform optimization, cost reduction, architecture simplification

```bash
# Find duplicate data views (high similarity pairs)
cja_auto_sdr --org-report --overlap-threshold 0.9 --format json --output - | \
  jq '.similarity_pairs[] | select(.similarity >= 0.9)'

# Note: For governance checks, pairs with >= 90% similarity are always included,
# even if `--overlap-threshold` is set above 0.9.
# Validate prod/staging alignment
cja_auto_sdr --org-report --filter "Prod|Staging" --overlap-threshold 0.95

# Analyze specific environment group
cja_auto_sdr --org-report --filter "^Marketing" --exclude "Test"

# Quick test with limited data views
cja_auto_sdr --org-report --limit 10
```

### Cross-Team Component Sharing

Identify components that could be shared across teams:
- Find **near-universal** components (in 70-99% of DVs) that should be standardized
- Identify **isolated** components that may be orphaned or redundant
- Track component adoption across business units

**Best for:** Platform teams, analytics CoE, component standardization

```bash
# Find standardization opportunities
cja_auto_sdr --org-report --format json --output - | \
  jq '.recommendations[] | select(.type == "standardization_opportunity")'

# Analyze isolated components per data view
cja_auto_sdr --org-report --format excel --include-names

# Quick summary without full analysis
cja_auto_sdr --org-report --skip-similarity
```

### Data View Clustering & Family Detection

Group related data views into clusters to understand organizational patterns:

**Best for:** Understanding data view relationships, identifying teams/domains, planning reorganization

```bash
# Enable clustering to find data view families
cja_auto_sdr --org-report --cluster --format excel

# Use different linkage methods
cja_auto_sdr --org-report --cluster --cluster-method complete

# Combine with metadata for owner context
cja_auto_sdr --org-report --cluster --include-metadata --owner-summary
```

### Trending & Drift Analysis

Track changes in your org's analytics landscape over time:

**Best for:** Quarterly reviews, detecting drift, compliance reporting

```bash
# Save baseline report
cja_auto_sdr --org-report --format json --output ./baselines/q1_2026.json

# Later, compare to baseline
cja_auto_sdr --org-report --compare-org-report ./baselines/q1_2026.json

# Shows:
# - Data views added/removed
# - Component count changes (↑ / ↓)
# - New high-similarity pairs
# - Resolved recommendations
```

### Naming Convention Audit

Detect and flag inconsistent naming patterns across your org:

**Best for:** Standardization initiatives, cleanup campaigns

```bash
# Run naming audit
cja_auto_sdr --org-report --audit-naming

# Flag stale components (test, old, temp patterns)
cja_auto_sdr --org-report --flag-stale

# Combined audit with full report
cja_auto_sdr --org-report --audit-naming --flag-stale --format excel
```

### Automated Governance Checks with Thresholds

Integrate org-wide governance into CI/CD pipelines with exit codes:

**Best for:** DevOps, automated compliance gates, deployment pipelines

```bash
# Exit with code 2 if more than 5 duplicate pairs exist
cja_auto_sdr --org-report --duplicate-threshold 5 --fail-on-threshold

# Exit with code 2 if isolated components exceed 30%
cja_auto_sdr --org-report --isolated-threshold 0.3 --fail-on-threshold

# Combined thresholds for comprehensive check
cja_auto_sdr --org-report \
  --duplicate-threshold 3 \
  --isolated-threshold 0.4 \
  --fail-on-threshold \
  --quiet
```

**CI/CD Integration for Governance:**

```yaml
# GitHub Actions - Weekly Governance Check
name: Org Governance Audit
on:
  schedule:
    - cron: '0 9 * * 1'  # Weekly Monday 9 AM

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install uv && uv sync

      - name: Generate Governance Report
        run: |
          cja_auto_sdr --org-report \
            --include-names \
            --format all \
            --output-dir ./reports
        env:
          ORG_ID: ${{ secrets.ORG_ID }}
          CLIENT_ID: ${{ secrets.CLIENT_ID }}
          SECRET: ${{ secrets.SECRET }}

      - uses: actions/upload-artifact@v4
        with:
          name: governance-reports
          path: ./reports/
```

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
| DevOps Engineers | CI/CD integration, governance gates | `--org-report --fail-on-threshold` in pipelines |
| Data Governance | Audit trails, component inventory, org-wide governance | Monthly `--org-report` + `--include-all-inventory` |
| Solution Architects | Complexity analysis, dependency mapping | `--include-all-inventory --inventory-only -f json` |
| Platform Teams | Org-wide standardization, duplicate detection | `--org-report --cluster --include-names --format excel` |
| Consultants | Multi-client management | Batch processing per client with profiles |
| Enterprise | Compliance documentation, cross-DV governance | `--org-report --compare-org-report` for trending |
| Technical Leads | Technical debt assessment, naming audits | `--org-report --audit-naming --flag-stale` |
| Analytics CoE | Component standardization, cross-team sharing | `--org-report --owner-summary --include-metadata` |

## See Also

- [Configuration Guide](CONFIGURATION.md) - config.json, environment variables, multi-environment setup
- [CLI Reference](CLI_REFERENCE.md) - All command options
- [Data View Comparison Guide](DIFF_COMPARISON.md) - Diff, snapshots, and CI/CD integration
- [Org-Wide Analysis Guide](ORG_WIDE_ANALYSIS.md) - Cross-data-view component analysis and governance
- [Segments Inventory](SEGMENTS_INVENTORY.md) - Segment filter documentation and complexity analysis
- [Derived Fields Inventory](DERIVED_FIELDS_INVENTORY.md) - Derived field logic and schema references
- [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) - Calculated metric formulas and dependencies
- [Performance Guide](PERFORMANCE.md) - Optimization tips
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Multi-view processing
- [Data Quality](DATA_QUALITY.md) - Understanding validation
- [Agent Automation Guide](AGENT_AUTOMATION.md) - Scheduling, CI/CD, and AI agent integration
