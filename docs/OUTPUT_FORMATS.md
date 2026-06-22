# Output Format Flexibility

The tool supports multiple output formats beyond Excel, providing flexible integration options for SDR generation, diff comparison, and org-wide analysis.

## Supported Formats

| Format | Description | Best For |
|--------|-------------|----------|
| **Excel** (.xlsx) | Formatted workbook with multiple sheets | Human review, reporting, documentation |
| **CSV** | Individual CSV files for each section | Data processing, spreadsheet import, automation |
| **JSON** | Hierarchical structured data | APIs, automation, integration with tools |
| **HTML** | Professional web-ready report | Web viewing, sharing, presentations |
| **Markdown** (.md) | GitHub/Confluence compatible tables | Documentation, version control, PRs |
| **Notion** | Notion page with structured blocks | Collaborative docs, Notion-based wikis |
| **Console** | Terminal output with ASCII formatting | Quick review, diff comparison, org-wide analysis, discovery |
| **All** | Generate all formats simultaneously (includes console in diff/org-wide modes) | Complete documentation package |

### Format Availability by Mode

| Format | SDR Generation | Diff Comparison | Org-Wide Analysis | Discovery |
|--------|----------------|-----------------|-------------------|-----------|
| Excel | ✓ (default) | ✓ | ✓ | ✗ |
| CSV | ✓ | ✓ | ✓ | ✓ |
| JSON | ✓ | ✓ | ✓ | ✓ |
| HTML | ✓ | ✓ | ✓ | ✗ |
| Markdown | ✓ | ✓ | ✓ | ✗ |
| Notion | ✓ | ✗ | ✓ (catalog only) | ✗ |
| Console/Table | ✗ | ✓ (default) | ✓ (default) | ✓ (default) |
| All | ✓ | ✓ | ✓ | ✗ |

> The Discovery column covers both discovery commands (`--list-dataviews`, `--list-connections`, `--list-datasets`) and discovery inspection commands (`--describe-dataview`, `--list-metrics`, `--list-dimensions`, `--list-segments`, `--list-calculated-metrics`). All output console (table), JSON, or CSV. They do not generate file-based formats like Excel, HTML, or Markdown.
>
> **Notion + Org-Wide Analysis:** `--org-report --format notion` writes a lightweight catalog row per data view (Name, Data View ID, Metrics/Dimensions Count, SDR Page link) and **requires a registry database** (`NOTION_DATABASE_ID` or `--notion-database-id`), since it writes only rows. Segments, Calculated Metrics, Derived Fields counts, and Data Quality are not populated. No detail pages are created. For complete rows, use `--batch <ids> --format notion`.

### Format Aliases (introduced in v3.2.0)

For convenience, format aliases provide shortcuts to common format combinations:

| Alias | Generates | Best For |
|-------|-----------|----------|
| `reports` | Excel + Markdown | Documentation and stakeholder sharing |
| `data` | CSV + JSON | Data pipelines, automation, integrations |
| `ci` | JSON + Markdown | CI/CD logs and PR comments |

```bash
# Generate Excel and Markdown reports
cja_auto_sdr dv_12345 --format reports

# Generate CSV and JSON for data pipelines
cja_auto_sdr dv_12345 --format data

# Generate JSON and Markdown for CI/CD
cja_auto_sdr --org-report --format ci
```

---

## Usage

### Command-Line Options

```bash
# Excel format (default)
cja_auto_sdr dv_12345

# CSV format
cja_auto_sdr dv_12345 --format csv

# JSON format
cja_auto_sdr dv_12345 --format json

# HTML format
cja_auto_sdr dv_12345 --format html

# Markdown format
cja_auto_sdr dv_12345 --format markdown

# All formats at once
cja_auto_sdr dv_12345 --format all

# Batch processing with CSV output
cja_auto_sdr --batch dv_12345 dv_67890 --format csv --workers 4
```

### Output Routing with `--output`

Use `--output` to specify the output file path, or write directly to stdout:

```bash
# Write JSON to specific file
cja_auto_sdr dv_12345 --format json --output ./reports/sdr.json

# Write to stdout (JSON/CSV only) for piping
cja_auto_sdr --list-dataviews --output -
cja_auto_sdr --list-dataviews --output stdout

# Pipe to other tools
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].id'

# Stats to stdout for scripting
cja_auto_sdr dv_12345 --stats --output -

# CSV stats to file
cja_auto_sdr dv_12345 --stats --format csv --output stats.csv
```

> **Note:** When using `--output -` or `--output stdout`, the `--quiet` flag is automatically enabled to prevent decorative output from mixing with the data.

---

## Format Details

### 1. Excel Format (.xlsx)

**Default format** - Professional formatted workbook with color-coding and styling.

**Output:**
- Single file: `CJA_DataView_{name}_{id}_SDR.xlsx`
- Multiple sheets (in order):
  1. Metadata
  2. Data Quality (color-coded by severity)
  3. DataView Details
  4. Metrics
  5. Dimensions
  6. Segments (if `--include-segments` specified)
  7. Derived Fields (if `--include-derived` specified)
  8. Calculated Metrics (if `--include-calculated` specified)

> **Sheet Ordering:** Inventory sheets (Segments, Derived Fields, Calculated Metrics) appear at the end of the workbook. When multiple are enabled, they appear in the order specified on the command line. For example, `--include-calculated --include-segments` places Calculated Metrics before Segments.
>
> **Inventory-Only Mode:** When `--inventory-only` is used, only sheets 6-8 are generated (requires at least one `--include-*` flag).

**Features:**
- Conditional formatting for data quality issues
- Auto-filtering on all sheets
- Frozen header rows
- Auto-adjusted column widths
- Alternating row colors
- Severity-based color coding (CRITICAL, HIGH, MEDIUM, LOW)

**Best for:**
- Manual review and analysis
- Stakeholder presentations
- Documentation archives
- Complex data exploration

---

### 2. CSV Format

**Output:**
- Directory: `{base_name}_csv/`
- Individual CSV files:
  - `metadata.csv`
  - `data_quality.csv`
  - `dataview_details.csv`
  - `metrics.csv`
  - `dimensions.csv`

**Features:**
- UTF-8 encoding
- Standard CSV format
- No index columns
- Header row included
- Compatible with all spreadsheet tools

**Best for:**
- Automated data processing
- ETL pipelines
- Database imports
- Custom analysis scripts
- Version control (text-based format)

**Example Use Case:**
```bash
# Export to CSV and process with pandas
cja_auto_sdr dv_12345 --format csv

# Then in Python:
import pandas as pd
metrics = pd.read_csv('CJA_DataView_myview_dv_12345_SDR_csv/metrics.csv')
# Perform custom analysis...
```

---

### 3. JSON Format

**Output:**
- Single file: `{base_name}.json`
- Hierarchical structure with metadata

**JSON Structure:**
```json
{
  "metadata": {
    "Generated At": "2024-01-01 12:00:00",
    "Data View ID": "dv_12345",
    "Data View Name": "My Data View",
    "Tool Version": "3.2.7",
    "Metrics Count": "150",
    "Dimensions Count": "75"
  },
  "data_view": {
    "Name": "My Data View",
    "ID": "dv_12345",
    "Owner": "user@example.com"
  },
  "metrics": [
    {
      "id": "metric1",
      "name": "Page Views",
      "type": "calculated",
      "description": "Total page views"
    }
  ],
  "dimensions": [
    {
      "id": "dim1",
      "name": "Page Name",
      "type": "string",
      "description": "Name of the page"
    }
  ],
  "data_quality": [
    {
      "Severity": "HIGH",
      "Category": "Duplicates",
      "Type": "Metrics",
      "Item Name": "Page Views",
      "Issue": "Duplicate name found",
      "Details": "..."
    }
  ]
}
```

**Features:**
- UTF-8 encoding with non-ASCII support
- Properly indented (2 spaces)
- Null values preserved
- Arrays for collections
- Objects for single records

**Best for:**
- API integrations
- Automation workflows
- JavaScript/Python processing
- Configuration management
- RESTful services
- DevOps pipelines

**Example Use Cases:**
```bash
# 1. API Integration
curl -X POST https://api.example.com/dataviews \
  -H "Content-Type: application/json" \
  -d @CJA_DataView_myview_dv_12345_SDR.json

# 2. Python Processing
import json
with open('CJA_DataView_myview_dv_12345_SDR.json') as f:
    data = json.load(f)
    metrics = data['metrics']
    for metric in metrics:
        print(f"{metric['name']}: {metric['description']}")

# 3. JavaScript/Node.js
const fs = require('fs');
const data = JSON.parse(fs.readFileSync('CJA_DataView_myview_dv_12345_SDR.json'));
console.log(`Metrics: ${data.metrics.length}`);
```

---

### 4. HTML Format

**Output:**
- Single file: `{base_name}.html`
- Self-contained with embedded CSS

**Features:**
- Professional modern styling
- Responsive design
- Color-coded data quality issues
- Sortable tables
- Hover effects
- Print-optimized CSS
- Metadata section with key-value pairs
- Section icons for visual clarity
- Sticky table headers

**Styling:**
- Modern color scheme
- Severity-based row highlighting:
  - CRITICAL: Red background
  - HIGH: Orange background
  - MEDIUM: Yellow background
  - LOW: Gray background
  - INFO: Blue background
- Alternating row colors for readability
- Hover highlighting
- Professional typography

**Best for:**
- Web sharing
- Email distribution
- Quick viewing in browsers
- Presentations
- Non-technical stakeholders
- Documentation portals

**Example:**
```bash
# Generate HTML and open in browser
cja_auto_sdr dv_12345 --format html
open CJA_DataView_myview_dv_12345_SDR.html  # macOS
# or
xdg-open CJA_DataView_myview_dv_12345_SDR.html  # Linux
# or
start CJA_DataView_myview_dv_12345_SDR.html  # Windows
```

---

### 5. Markdown Format (.md)

**Output:**
- Single file: `{base_name}.md`
- GitHub-flavored markdown with tables

**Features:**
- Table of contents with navigation links
- Component tables with all fields
- Data quality section with severity indicators
- Collapsible sections for large data
- Metadata header with generation info
- Compatible with GitHub, GitLab, Confluence

**Structure:**
```markdown
# SDR: Data View Name

## Table of Contents
- [Metadata](#metadata)
- [Data Quality](#data-quality)
- [Metrics](#metrics)
- [Dimensions](#dimensions)

## Metadata
| Field | Value |
|-------|-------|
| Data View Name | Production Analytics |
| ID | dv_12345 |
...

## Data Quality
| Severity | Category | Type | Issue |
|----------|----------|------|-------|
| HIGH | Duplicates | Metrics | ... |
...

## Metrics (150 total)
| ID | Name | Description | Type |
|----|------|-------------|------|
...

## Dimensions (75 total)
| ID | Name | Description | Schema Path |
|----|------|-------------|-------------|
...
```

**Best for:**
- Documentation repositories
- GitHub/GitLab wikis
- Confluence pages
- Version control tracking
- Pull request attachments
- Technical documentation

**Example:**
```bash
# Generate markdown report
cja_auto_sdr dv_12345 --format markdown

# View in terminal
cat CJA_DataView_myview_dv_12345_SDR.md

# Convert to PDF with pandoc (if installed)
pandoc CJA_DataView_myview_dv_12345_SDR.md -o report.pdf
```

---

### 6. Notion Format

Publishes the SDR directly to a Notion page and (optionally) upserts a row in a "CJA SDR Registry" database. Requires `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID` environment variables and the `notion` optional extra (`uv pip install 'cja-auto-sdr[notion]'`).

Each run creates or updates a single page under the configured parent. Page IDs are tracked in `.notion_pages.json` in the output directory so re-runs update in place rather than accumulating duplicates.

**Usage:**
```bash
# Publish SDR directly to Notion
cja_auto_sdr dv_12345 --format notion

# Force a new page even if one already exists
cja_auto_sdr dv_12345 --format notion --notion-force-new

# Push an existing JSON artifact to Notion (no CJA API call)
cja_auto_sdr --push-to-notion ./reports/dv_12345_sdr.json

# Publish and upsert a registry row (requires NOTION_DATABASE_ID)
export NOTION_DATABASE_ID=<database-id>
cja_auto_sdr dv_12345 --format notion

# Create a new registry database during a publish run and capture its ID
cja_auto_sdr dv_12345 --format notion --notion-create-database
```

**Block layout:**
- Metadata callout (data view name, ID, timestamp, version)
- Data Quality callouts (one per issue, severity-coded; omitted if none)
- Heading + inline table for Metrics, Dimensions, Segments, Calculated Metrics, Derived Fields
- Empty sections are omitted automatically
- Footer paragraph with tool version

**Behaviour and caveats:**
- **Auto-regenerated pages overwrite manual edits.** When the registry contains a page ID for the data view, the writer clears every child block before re-appending the freshly generated SDR. Any annotations, comments-as-blocks, or layout changes a user added inside Notion will be lost on the next run. Use `--notion-force-new` to break the registry link and produce a new page (the old one is recorded as an orphan in `.notion_pages.json`) when you need to preserve manual edits.
- **Orphan tracking and pruning (v3.9.0).** Each time `--notion-force-new` forces a replacement page, the superseded page ID is stored as an orphan in `.notion_pages.json`. Run `--notion-prune-orphans` to archive those pages (sent to Notion trash — recoverable, not permanently deleted) and clear them from the registry. Use `--notion-prune-orphans --dry-run` to preview which pages would be archived without making any changes. **Limitation:** only pages orphaned by `--notion-force-new` from v3.9.0 onward are tracked; pages left behind by earlier runs are not catalogued and are unaffected by pruning.
- **`--push-to-notion` is mutually exclusive with all other generation flags.** Combining it with `--org-report`, `--diff`, `--snapshot`, `--batch`, `--watch`, `--inventory-summary`, `--dry-run`, or positional data view IDs exits with an actionable error (rather than silently dropping `--push-to-notion`).
- **Large sections split into sibling tables.** Notion caps a block's children array at 100. Sections with more than 99 data rows are split into multiple sibling tables under the same heading, preserving row order.
- **API failures surface as friendly messages.** Missing/invalid `NOTION_TOKEN`, deleted parent pages, and rate-limit errors print a one-line summary and exit 1; 429 responses are retried with exponential backoff (or `Retry-After` if Notion provides it) before giving up.
- **`--workers > 1` and `--watch` are rejected** with exit 1 when `--format notion` is active. Use `--batch <ids> --format notion` for multiple data views.

#### Notion Registry Database (v3.8.0)

When `NOTION_DATABASE_ID` is set (or `--notion-database-id` is passed), every `--format notion` run upserts a row in the "CJA SDR Registry" database, keyed by Data View ID. If the env var and flag are both unset, no row is written (v3.7.0 behavior preserved).

**Registry properties (14 total):**

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Data view display name |
| Data View ID | Text | CJA data view ID (e.g. `dv_abc123`) — primary key for upsert |
| SDR Page | URL | `notion://pages/<page_id>` string pointing to the detail page (NOT a Notion relation) |
| Last Updated | Date | Timestamp of the most recent upsert |
| Tool Version | Text | `cja-auto-sdr` version that wrote the row |
| Captured At | Date | When the data was captured from the CJA API |
| Currency | Text | Data view currency setting |
| Timezone | Text | Data view timezone setting |
| Metrics Count | Number | Total metrics in the data view |
| Dimensions Count | Number | Total dimensions in the data view |
| Segments Count | Number | Total segments scoped to the data view |
| Calculated Metrics Count | Number | Total calculated metrics for the data view |
| Derived Fields Count | Number | Total derived fields in the data view |
| Data Quality | Select | Worst data-quality severity as a status (`healthy`, `degraded`, `partial`, `unknown`) |

> **`SDR Page` is a URL string, not a Notion relation.** The property holds `notion://pages/<id>` as plain text. This avoids permission constraints that would prevent cross-database relations in most Notion workspace configurations.
>
> **Registry file v1 → v2 migration:** `.notion_pages.json` previously stored a plain page ID string per data view. From v3.8.0 it stores `{"page_id": "...", "database_row_id": "..."}`. Legacy v1 entries are read transparently and rewritten to v2 format on the next sync — no manual migration is needed.

**Bootstrap workflow:**

```bash
# 1. Create the registry database on your first publish (needs a data view + --format notion)
cja_auto_sdr dv_12345 --format notion --notion-create-database
# Prints the new database ID  ← capture it

# 2. Add the database ID to your environment
export NOTION_DATABASE_ID=<id>  # or add to .env

# 3. Publish data views — detail page + complete registry row
cja_auto_sdr dv_12345 --format notion
cja_auto_sdr --batch dv_12345 dv_67890 dv_abcde --format notion
```

**Inspecting and repairing the schema (v3.10.0):**

The canonical registry schema can be printed at any time without credentials:

```bash
cja_auto_sdr --notion-print-database-schema
```

When the schema grows across tool versions, use `--notion-repair-database` instead of recreating the database. It is add-only: it adds any missing properties and reports type conflicts, but never changes or removes existing properties or data rows. Requires only `NOTION_TOKEN` and a database id:

```bash
# Preview what would be added (no changes made)
cja_auto_sdr --notion-repair-database --dry-run --notion-database-id <id>

# Apply the repair
cja_auto_sdr --notion-repair-database --notion-database-id <id>
```

**Org-report catalog (lightweight):**

`--org-report --format notion` writes one registry row per data view from the org report summary. Because it writes only rows (no detail pages), it **requires a registry database** — set `NOTION_DATABASE_ID` or pass `--notion-database-id <id>` (running it without one exits with an error). It fills Name, Data View ID, Metrics Count, Dimensions Count, owner/dates, and an SDR Page link where a detail page already exists. The following columns are **not** populated because the org report does not fetch that data:

- Segments Count
- Calculated Metrics Count
- Derived Fields Count
- Data Quality (shows `unknown`)

Detail pages are not created. For complete rows with all counts and linked detail pages, use `--batch <ids> --format notion` instead. Full org-report detail-page generation is planned for a future release.

---

### 7. All Formats

Generate all output formats in a single run for complete documentation packages.

**Output (SDR mode):**
- `CJA_DataView_{name}_{id}_SDR.xlsx` (Excel)
- `CJA_DataView_{name}_{id}_SDR_csv/` (CSV directory)
- `CJA_DataView_{name}_{id}_SDR.json` (JSON)
- `CJA_DataView_{name}_{id}_SDR.html` (HTML)
- `CJA_DataView_{name}_{id}_SDR.md` (Markdown)

**Output (diff/org-wide modes):**
- All file formats above, plus console output displayed in terminal

**Example:**
```bash
# Generate complete documentation package (SDR)
cja_auto_sdr dv_12345 --format all --output-dir ./documentation

# Generate all formats including console output (diff mode)
cja_auto_sdr --diff dv_12345 dv_67890 --format all --output-dir ./reports
```

**Best for:**
- Archival purposes
- Multi-audience distribution
- Compliance requirements
- Complete documentation packages

---

## Integration Examples

### 1. Automated Daily Reports

```bash
#!/bin/bash
# daily_report.sh - Generate daily SDR in HTML for web viewing

DATE=$(date +%Y%m%d)
OUTPUT_DIR="./reports/$DATE"

cja_auto_sdr \
  --batch dv_12345 dv_67890 \
  --format html \
  --output-dir "$OUTPUT_DIR" \
  --workers 4

# Upload to web server
rsync -avz "$OUTPUT_DIR/" user@webserver:/var/www/reports/
```

### 2. JSON API Integration

```python
# api_integration.py - Upload SDR data to monitoring API

import json
import requests
import subprocess

# Generate JSON output
subprocess.run([
    'cja_auto_sdr',
    'dv_12345',
    '--format', 'json'
])

# Load and send to API
with open('CJA_DataView_myview_dv_12345_SDR.json') as f:
    data = json.load(f)

response = requests.post(
    'https://monitoring.example.com/api/dataviews',
    json=data,
    headers={'Authorization': 'Bearer token123'}
)

print(f"Upload status: {response.status_code}")
```

### 3. CSV Data Pipeline

```python
# data_pipeline.py - Process CSV exports for analysis

import pandas as pd
import subprocess

# Generate CSV outputs
subprocess.run([
    'cja_auto_sdr',
    'dv_12345',
    '--format', 'csv'
])

# Load and process
csv_dir = 'CJA_DataView_myview_dv_12345_SDR_csv'
metrics = pd.read_csv(f'{csv_dir}/metrics.csv')
dimensions = pd.read_csv(f'{csv_dir}/dimensions.csv')
quality = pd.read_csv(f'{csv_dir}/data_quality.csv')

# Perform analysis
critical_issues = quality[quality['Severity'] == 'CRITICAL']
print(f"Critical issues found: {len(critical_issues)}")

# Export to database
metrics.to_sql('cja_metrics', con=db_connection, if_exists='replace')
dimensions.to_sql('cja_dimensions', con=db_connection, if_exists='replace')
```

### 4. Multi-Format Batch Processing

```bash
#!/bin/bash
# comprehensive_audit.sh - Generate comprehensive audit package

DATA_VIEWS=(
  "dv_12345"
  "dv_67890"
  "dv_abcde"
)

for dv in "${DATA_VIEWS[@]}"; do
  echo "Processing $dv..."

  # Generate all formats
  cja_auto_sdr "$dv" \
    --format all \
    --output-dir "./audit/$(date +%Y-%m-%d)/$dv"
done

echo "Audit package complete!"
```

---

## File Size Comparison

Typical output sizes for a data view with 150 metrics and 75 dimensions:

| Format | File Size | Compression | Notes |
|--------|-----------|-------------|-------|
| Excel (.xlsx) | ~250 KB | Native compression | Includes formatting |
| CSV (all files) | ~180 KB | None | Text-based, compresses well |
| JSON | ~200 KB | None | Human-readable structure |
| HTML | ~300 KB | None | Includes embedded CSS |

**Tip:** CSV and JSON formats compress very well with gzip (60-80% reduction).

---

## Performance

### Generation Time (Single Data View)

| Format | Time | Relative |
|--------|------|----------|
| Excel | 1.2s | 1.0x |
| CSV | 0.3s | 0.25x |
| JSON | 0.2s | 0.17x |
| HTML | 0.4s | 0.33x |
| Markdown | 0.3s | 0.25x |
| All | 2.4s | 2.0x |

### Batch Processing (10 Data Views, 4 workers)

| Format | Total Time | Per View |
|--------|------------|----------|
| Excel | 35s | 3.5s |
| CSV | 25s | 2.5s |
| JSON | 22s | 2.2s |
| HTML | 28s | 2.8s |
| Markdown | 26s | 2.6s |
| All | 50s | 5.0s |

---

## Use Case Recommendations

### Excel - When to Use

- Manual analysis and review
- Stakeholder presentations
- Complex formatting requirements
- Color-coded visualization needs
- Multi-sheet organization

### CSV - When to Use

- Automated data processing
- ETL pipelines
- Database imports
- Version control tracking
- Programming language integration

### JSON - When to Use

- API integrations
- Automation workflows
- Configuration management
- JavaScript/Python processing
- Microservices communication

### HTML - When to Use

- Web-based viewing
- Email distribution
- Non-technical audiences
- Quick browser access
- Documentation portals

### Markdown - When to Use

- Documentation repositories (GitHub, GitLab)
- Confluence/wiki pages
- Version control tracking
- Pull request attachments
- Technical documentation
- Text-based archival

### All - When to Use

- Comprehensive documentation
- Archival requirements
- Multi-audience distribution
- Compliance documentation

---

## Testing

The implementation includes 37 comprehensive tests covering:

- CSV file generation and data integrity
- JSON structure and validity
- HTML generation and styling
- Markdown table formatting and TOC generation
- Cross-format data consistency
- Edge cases (empty data, Unicode, special characters)
- Large dataset handling

Run tests:

```bash
# Test all output formats
uv run pytest tests/test_output_formats.py -v

# Test specific format
uv run pytest tests/test_output_formats.py::TestCSVOutput -v
uv run pytest tests/test_output_formats.py::TestJSONOutput -v
uv run pytest tests/test_output_formats.py::TestHTMLOutput -v
uv run pytest tests/test_output_formats.py::TestMarkdownOutput -v
```

---

## Migration Guide

### From Excel-only to Multi-format

**Before:**

```bash
cja_auto_sdr dv_12345
# Always generates Excel
```

**After:**

```bash
# Explicit Excel (same as before)
cja_auto_sdr dv_12345 --format excel

# Or choose other formats
cja_auto_sdr dv_12345 --format csv
cja_auto_sdr dv_12345 --format json
cja_auto_sdr dv_12345 --format html
cja_auto_sdr dv_12345 --format markdown
cja_auto_sdr dv_12345 --format all
```

**Backward Compatibility:** The default format is Excel, so existing scripts continue to work without changes.

---

## Troubleshooting

### Issue: CSV files have encoding problems

**Solution:** CSV files are UTF-8 encoded. Use `encoding='utf-8'` when reading:

```python
df = pd.read_csv('file.csv', encoding='utf-8')
```

### Issue: JSON file is too large to process

**Solution:** Stream the JSON data or use JSON streaming libraries:

```python
import ijson
with open('large.json', 'rb') as f:
    metrics = ijson.items(f, 'metrics.item')
    for metric in metrics:
        process(metric)
```

### Issue: HTML doesn't display correctly

**Solution:** Ensure you're viewing in a modern browser (Chrome, Firefox, Safari, Edge). The HTML uses modern CSS features.

### Issue: Need specific CSV encoding

**Modification:** Edit `write_csv_output()` in `src/cja_auto_sdr/generator.py` to change encoding:

```python
df.to_csv(csv_file, index=False, encoding='latin1')  # or other encoding
```

---

## Summary

Output format flexibility provides:

- **Multiple Format Options:** Excel, CSV, JSON, HTML, Markdown, or all
- **Easy CLI Selection:** Simple `--format` flag
- **Consistent Data:** Same data in all formats
- **Optimized for Use Cases:** Right format for the right purpose
- **Fully Tested:** 37 comprehensive tests
- **Production Ready:** Zero breaking changes

**Result:** Flexible integration options for automation, APIs, web viewing, documentation, and traditional reporting.

---

## Org-Wide Analysis Output (introduced in v3.2.0)

The org-wide analysis mode (`--org-report`) generates specialized output showing component distribution across all data views.

### Console Output (Default)

```bash
# Console output with distribution buckets
cja_auto_sdr --org-report
```

Output includes:
- **Distribution Summary:** Core, Common, Limited, Isolated component counts
- **Similarity Matrix:** Jaccard similarity between data views (unless `--skip-similarity`). For governance checks, the effective overlap threshold is capped at 90% and reports note the configured vs. effective threshold when higher.
- **Governance Recommendations:** Based on component distribution patterns

### Excel/File Output

```bash
# Full org report in Excel
cja_auto_sdr --org-report --format excel

# Quick stats only (minimal output)
cja_auto_sdr --org-report --org-stats

# All formats for comprehensive documentation
cja_auto_sdr --org-report --format all --output-dir ./reports
```

Excel sheets include:
- **Summary:** Organization overview and statistics
- **Component Distribution:** Core, Common, Limited, Isolated buckets
- **Similarity Matrix:** Data view similarity scores
- **Data View Details:** Per-data-view component breakdown

### Trending and Comparison

```bash
# Compare org reports over time
cja_auto_sdr --org-report --compare-org-report ./previous_report.json

# Export for later comparison
cja_auto_sdr --org-report --format json --output ./current_report.json
```

See [Org-Wide Analysis](ORG_WIDE_ANALYSIS.md) for detailed documentation.

---

## Inventory Sheets

### Segments Inventory

When `--include-segments` is specified, a "Segments" sheet/section is added with:
- Complexity scores (0-100)
- Container types (Hit/Visit/Person)
- Definition summaries (human-readable)
- Dimension, metric, and segment references
- Governance info (approved, tags, owner)

```bash
cja_auto_sdr dv_12345 --include-segments
```

See [Segments Inventory](SEGMENTS_INVENTORY.md) for detailed documentation.

### Derived Field Inventory

When `--include-derived` is specified, a "Derived Fields" sheet/section is added with:
- Complexity scores (0-100)
- Functions used
- Schema field references
- Logic summaries

```bash
cja_auto_sdr dv_12345 --include-derived
```

See [Derived Field Inventory](DERIVED_FIELDS_INVENTORY.md) for detailed documentation.

### Calculated Metrics Inventory

When `--include-calculated` is specified, a "Calculated Metrics" sheet/section is added with:
- Complexity scores (0-100)
- Formula summaries
- Metric and segment references
- Owner information

```bash
cja_auto_sdr dv_12345 --include-calculated
```

See [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) for detailed documentation.

### Combining Inventories

All three inventories can be included together. The sheets appear at the end of the output in CLI argument order:

```bash
# All three inventories (Segments first)
cja_auto_sdr dv_12345 --include-segments --include-derived --include-calculated

# Custom order (Calculated Metrics first)
cja_auto_sdr dv_12345 --include-calculated --include-segments --include-derived
```

### Inventory-Only Mode

Use `--inventory-only` to generate only inventory sheets without standard SDR content:

```bash
# Segments inventory only (no Metadata, Data Quality, etc.)
cja_auto_sdr dv_12345 --include-segments --inventory-only

# Multiple inventories only
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived --inventory-only

# Output in multiple formats
cja_auto_sdr dv_12345 --include-segments --inventory-only -f all
```

> **Note:** `--inventory-only` requires at least one `--include-*` flag.

---

## See Also

- [Configuration Guide](CONFIGURATION.md) - Setup and output directory options
- [CLI Reference](CLI_REFERENCE.md) - Complete output options
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Multi-format batch output
- [Org-Wide Analysis](ORG_WIDE_ANALYSIS.md) - Org report output options
- [Data Quality Guide](DATA_QUALITY.md) - Understanding the Data Quality sheet
- [Segments Inventory](SEGMENTS_INVENTORY.md) - Segment filter analysis
- [Derived Field Inventory](DERIVED_FIELDS_INVENTORY.md) - Derived field analysis
- [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) - Calculated metrics analysis
