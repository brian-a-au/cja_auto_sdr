#!/usr/bin/env python3
"""
Create sample output files to demonstrate all formats

This creates mock outputs without requiring CJA credentials
"""

import pandas as pd
import json
from datetime import datetime
from pathlib import Path

# Create sample data
sample_metadata = {
    'Generation Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z'),
    'Data View ID': 'dv_sample_12345',
    'Data View Name': 'Sample Production Analytics',
    'Total Metrics': 25,
    'Total Dimensions': 15,
    'Tool Version': '3.0.16'
}

sample_quality_issues = pd.DataFrame([
    {
        'Severity': 'HIGH',
        'Category': 'Duplicates',
        'Type': 'Metrics',
        'Item Name': 'Page Views',
        'Issue': 'Duplicate name found 2 times',
        'Details': 'This metrics name appears 2 times in the data view'
    },
    {
        'Severity': 'MEDIUM',
        'Category': 'Null Values',
        'Type': 'Dimensions',
        'Item Name': 'Product Category',
        'Issue': 'Null values in "description" field',
        'Details': 'Missing description for better documentation'
    },
    {
        'Severity': 'LOW',
        'Category': 'Missing Fields',
        'Type': 'Metrics',
        'Item Name': 'Conversion Rate',
        'Issue': 'Missing description',
        'Details': 'Description field is empty'
    }
])

sample_metrics = pd.DataFrame([
    {
        'id': 'metrics/pageviews',
        'name': 'Page Views',
        'type': 'int',
        'title': 'Page Views',
        'description': 'Total number of page views',
        'dataType': 'integer',
        'precision': 0
    },
    {
        'id': 'metrics/visits',
        'name': 'Visits',
        'type': 'int',
        'title': 'Visits',
        'description': 'Total number of visits',
        'dataType': 'integer',
        'precision': 0
    },
    {
        'id': 'metrics/revenue',
        'name': 'Revenue',
        'type': 'currency',
        'title': 'Revenue',
        'description': 'Total revenue in USD',
        'dataType': 'decimal',
        'precision': 2
    }
])

sample_dimensions = pd.DataFrame([
    {
        'id': 'variables/evar1',
        'name': 'Campaign',
        'type': 'string',
        'title': 'Marketing Campaign',
        'description': 'Marketing campaign tracking code',
        'dataType': 'string'
    },
    {
        'id': 'variables/evar2',
        'name': 'Product Category',
        'type': 'string',
        'title': 'Product Category',
        'description': 'Product category classification',
        'dataType': 'string'
    }
])

def create_csv_outputs():
    """Create CSV outputs"""
    print("\n1. Creating CSV outputs...")
    output_dir = Path("sample_outputs/csv")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create metadata CSV
    pd.DataFrame([sample_metadata]).to_csv(
        output_dir / "metadata.csv", index=False
    )

    # Create quality issues CSV
    sample_quality_issues.to_csv(
        output_dir / "data_quality.csv", index=False
    )

    # Create metrics CSV
    sample_metrics.to_csv(
        output_dir / "metrics.csv", index=False
    )

    # Create dimensions CSV
    sample_dimensions.to_csv(
        output_dir / "dimensions.csv", index=False
    )

    print(f"   ✓ Created 4 CSV files in {output_dir}")

def create_json_output():
    """Create JSON output"""
    print("\n2. Creating JSON output...")
    output_dir = Path("sample_outputs/json")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_data = {
        'metadata': sample_metadata,
        'data_quality': sample_quality_issues.to_dict('records'),
        'metrics': sample_metrics.to_dict('records'),
        'dimensions': sample_dimensions.to_dict('records')
    }

    output_file = output_dir / "sample_sdr.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"   ✓ Created {output_file}")

def create_html_output():
    """Create HTML output"""
    print("\n3. Creating HTML output...")
    output_dir = Path("sample_outputs/html")
    output_dir.mkdir(parents=True, exist_ok=True)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CJA SDR - Sample Production Analytics</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1 {{
            margin: 0 0 10px 0;
            font-size: 2em;
        }}
        .metadata {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        th {{
            background: #4a5568;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #e2e8f0;
        }}
        tr:hover {{
            background: #f7fafc;
        }}
        .severity-HIGH {{
            background: #fed7d7;
            color: #c53030;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .severity-MEDIUM {{
            background: #feebc8;
            color: #c05621;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .severity-LOW {{
            background: #bee3f8;
            color: #2c5282;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        h2 {{
            color: #2d3748;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
            margin-top: 30px;
        }}
        .footer {{
            text-align: center;
            color: #718096;
            margin-top: 40px;
            padding: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Customer Journey Analytics</h1>
        <h2 style="margin: 0; font-weight: 300;">Solution Design Reference</h2>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">Generated with v3.0.16</p>
    </div>

    <div class="metadata">
        <h2>Metadata</h2>
        <table>
            <tr><td><strong>Data View ID:</strong></td><td>{sample_metadata['Data View ID']}</td></tr>
            <tr><td><strong>Data View Name:</strong></td><td>{sample_metadata['Data View Name']}</td></tr>
            <tr><td><strong>Generated:</strong></td><td>{sample_metadata['Generation Timestamp']}</td></tr>
            <tr><td><strong>Total Metrics:</strong></td><td>{sample_metadata['Total Metrics']}</td></tr>
            <tr><td><strong>Total Dimensions:</strong></td><td>{sample_metadata['Total Dimensions']}</td></tr>
            <tr><td><strong>Tool Version:</strong></td><td>{sample_metadata['Tool Version']}</td></tr>
        </table>
    </div>

    <div class="section">
        <h2>Data Quality Issues</h2>
        <table>
            <thead>
                <tr>
                    <th>Severity</th>
                    <th>Category</th>
                    <th>Type</th>
                    <th>Item Name</th>
                    <th>Issue</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
"""

    for _, row in sample_quality_issues.iterrows():
        html_content += f"""                <tr>
                    <td><span class="severity-{row['Severity']}">{row['Severity']}</span></td>
                    <td>{row['Category']}</td>
                    <td>{row['Type']}</td>
                    <td>{row['Item Name']}</td>
                    <td>{row['Issue']}</td>
                    <td>{row['Details']}</td>
                </tr>
"""

    html_content += """            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Metrics</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Title</th>
                    <th>Description</th>
                </tr>
            </thead>
            <tbody>
"""

    for _, row in sample_metrics.iterrows():
        html_content += f"""                <tr>
                    <td>{row['id']}</td>
                    <td>{row['name']}</td>
                    <td>{row['type']}</td>
                    <td>{row['title']}</td>
                    <td>{row['description']}</td>
                </tr>
"""

    html_content += """            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Dimensions</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Title</th>
                    <th>Description</th>
                </tr>
            </thead>
            <tbody>
"""

    for _, row in sample_dimensions.iterrows():
        html_content += f"""                <tr>
                    <td>{row['id']}</td>
                    <td>{row['name']}</td>
                    <td>{row['type']}</td>
                    <td>{row['title']}</td>
                    <td>{row['description']}</td>
                </tr>
"""

    html_content += """            </tbody>
        </table>
    </div>

    <div class="footer">
        <p>Generated by CJA Auto SDR Generator v3.0.16</p>
        <p>Features: Validation Caching • Parallel Processing • Optimized Validation</p>
    </div>
</body>
</html>
"""

    output_file = output_dir / "sample_sdr.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"   ✓ Created {output_file}")

def create_markdown_output():
    """Create Markdown output"""
    print("\n4. Creating Markdown output...")
    output_dir = Path("sample_outputs/markdown")
    output_dir.mkdir(parents=True, exist_ok=True)

    md_content = """# 📊 CJA Solution Design Reference

## 📋 Metadata

**Generation Timestamp:** {timestamp}
**Data View ID:** {dv_id}
**Data View Name:** {dv_name}
**Total Metrics:** {metrics_count}
**Total Dimensions:** {dims_count}
**Tool Version:** {version}

## 📑 Table of Contents

- [Data Quality](#data-quality)
- [Metrics](#metrics)
- [Dimensions](#dimensions)

---

## Data Quality

### Issue Summary

| Severity | Count |
| --- | --- |
| 🟠 HIGH | 1 |
| 🟡 MEDIUM | 1 |
| ⚪ LOW | 1 |

### All Issues

| Severity | Category | Type | Item Name | Issue | Details |
| --- | --- | --- | --- | --- | --- |
| HIGH | Duplicates | Metrics | Page Views | Duplicate name found 2 times | This metrics name appears 2 times in the data view |
| MEDIUM | Null Values | Dimensions | Product Category | Null values in "description" field | Missing description for better documentation |
| LOW | Missing Fields | Metrics | Conversion Rate | Missing description | Description field is empty |

---

## Metrics

| id | name | type | title | description | dataType | precision |
| --- | --- | --- | --- | --- | --- | --- |
| metrics/pageviews | Page Views | int | Page Views | Total number of page views | integer | 0 |
| metrics/visits | Visits | int | Visits | Total number of visits | integer | 0 |
| metrics/revenue | Revenue | currency | Revenue | Total revenue in USD | decimal | 2 |

---

## Dimensions

| id | name | type | title | description | dataType |
| --- | --- | --- | --- | --- | --- |
| variables/evar1 | Campaign | string | Marketing Campaign | Marketing campaign tracking code | string |
| variables/evar2 | Product Category | string | Product Category | Product category classification | string |

---

*Generated by CJA Auto SDR Generator v3.0.16*
""".format(
        timestamp=sample_metadata['Generation Timestamp'],
        dv_id=sample_metadata['Data View ID'],
        dv_name=sample_metadata['Data View Name'],
        metrics_count=sample_metadata['Total Metrics'],
        dims_count=sample_metadata['Total Dimensions'],
        version=sample_metadata['Tool Version']
    )

    output_file = output_dir / "sample_sdr.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"   ✓ Created {output_file}")

def create_excel_output():
    """Create Excel output using xlsxwriter"""
    print("\n5. Creating Excel output...")
    import xlsxwriter

    output_dir = Path("sample_outputs/excel")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "sample_sdr.xlsx"
    workbook = xlsxwriter.Workbook(output_file)

    # Define formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4a5568',
        'font_color': 'white',
        'border': 1
    })

    severity_formats = {
        'HIGH': workbook.add_format({'bg_color': '#fed7d7', 'font_color': '#c53030'}),
        'MEDIUM': workbook.add_format({'bg_color': '#feebc8', 'font_color': '#c05621'}),
        'LOW': workbook.add_format({'bg_color': '#bee3f8', 'font_color': '#2c5282'})
    }

    # Metadata sheet
    ws_meta = workbook.add_worksheet('Metadata')
    row = 0
    for key, value in sample_metadata.items():
        ws_meta.write(row, 0, key, header_format)
        ws_meta.write(row, 1, str(value))
        row += 1
    ws_meta.set_column(0, 0, 25)
    ws_meta.set_column(1, 1, 40)

    # Data Quality sheet
    ws_quality = workbook.add_worksheet('Data Quality')
    for col, header in enumerate(sample_quality_issues.columns):
        ws_quality.write(0, col, header, header_format)

    for row_idx, row_data in enumerate(sample_quality_issues.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row_data):
            if col_idx == 0:  # Severity column
                ws_quality.write(row_idx, col_idx, value, severity_formats.get(value))
            else:
                ws_quality.write(row_idx, col_idx, value)

    ws_quality.autofilter(0, 0, len(sample_quality_issues), len(sample_quality_issues.columns)-1)

    # Metrics sheet
    ws_metrics = workbook.add_worksheet('Metrics')
    for col, header in enumerate(sample_metrics.columns):
        ws_metrics.write(0, col, header, header_format)

    for row_idx, row_data in enumerate(sample_metrics.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row_data):
            ws_metrics.write(row_idx, col_idx, value)

    ws_metrics.autofilter(0, 0, len(sample_metrics), len(sample_metrics.columns)-1)

    # Dimensions sheet
    ws_dims = workbook.add_worksheet('Dimensions')
    for col, header in enumerate(sample_dimensions.columns):
        ws_dims.write(0, col, header, header_format)

    for row_idx, row_data in enumerate(sample_dimensions.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row_data):
            ws_dims.write(row_idx, col_idx, value)

    ws_dims.autofilter(0, 0, len(sample_dimensions), len(sample_dimensions.columns)-1)

    workbook.close()
    print(f"   ✓ Created {output_file}")

def main():
    print("=" * 70)
    print("  Creating Sample Output Files - v3.0.16")
    print("=" * 70)
    print("\nGenerating sample outputs in all supported formats:")

    create_csv_outputs()
    create_json_output()
    create_html_output()
    create_markdown_output()
    create_excel_output()

    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    print("\nSample outputs created successfully:")
    print("  • CSV:      sample_outputs/csv/")
    print("  • JSON:     sample_outputs/json/sample_sdr.json")
    print("  • HTML:     sample_outputs/html/sample_sdr.html")
    print("  • Markdown: sample_outputs/markdown/sample_sdr.md")
    print("  • Excel:    sample_outputs/excel/sample_sdr.xlsx")
    print("\nOpen the HTML file in a browser or Markdown in GitHub to see the formatted report!")
    print("\n✓ All output formats generated successfully")

if __name__ == '__main__':
    main()
