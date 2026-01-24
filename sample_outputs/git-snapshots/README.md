# Sample Git Snapshots

This directory contains example files demonstrating the Git integration snapshot format used by the CJA SDR Generator.

## Directory Structure

```
git-snapshots/
└── ProductionAnalytics_dv_12345/
    ├── metrics.json      # All metrics, sorted by ID
    ├── dimensions.json   # All dimensions, sorted by ID
    └── metadata.json     # Data view info and quality summary
```

## File Descriptions

### metrics.json

Contains all metrics from the data view, sorted by ID for consistent Git diffs.

```json
[
  {
    "id": "cm_revenue",
    "name": "Revenue",
    "type": "currency",
    "description": "Total revenue in USD"
  }
]
```

### dimensions.json

Contains all dimensions from the data view, sorted by ID for consistent Git diffs.

```json
[
  {
    "id": "dim_browser",
    "name": "Browser",
    "type": "string",
    "description": "User's web browser"
  }
]
```

### metadata.json

Contains data view metadata, component counts, and quality issue summary.

```json
{
  "snapshot_version": "1.0",
  "created_at": "2026-01-19T10:30:00.000000",
  "data_view_id": "dv_12345",
  "data_view_name": "Production Analytics",
  "owner": "analytics-team",
  "description": "Main production data view",
  "tool_version": "3.0.14",
  "summary": {
    "metrics_count": 5,
    "dimensions_count": 5,
    "total_components": 10
  },
  "quality": {
    "total_issues": 2,
    "by_severity": {
      "HIGH": 0,
      "MEDIUM": 1,
      "LOW": 1
    }
  }
}
```

## Why This Format?

- **Sorted by ID**: Consistent ordering means minimal noise in Git diffs
- **Separate Files**: Changes to metrics don't show up in dimensions diff
- **Human Readable**: JSON with indentation for easy inspection
- **Git-Friendly**: Clean diffs for code review and PR workflows

## Usage

To generate these snapshots for your own data views:

```bash
# Initialize Git repository (one-time setup)
cja_auto_sdr --git-init --git-dir ./sdr-snapshots

# Generate SDR and commit to Git
cja_auto_sdr dv_YOUR_ID --git-commit

# View commit history
cd sdr-snapshots && git log --oneline
```

See the [Git Integration Guide](../../docs/GIT_INTEGRATION.md) for complete documentation.
