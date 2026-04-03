"""Inventory summary display — presentation logic for inventory mode.

Renders inventory summary statistics to the console and writes JSON summary
files.  Extracted from generator.py; the orchestration function
``process_inventory_summary`` remains there.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.json_io import write_json_atomic_compatible


def display_inventory_summary(
    data_view_id: str,
    data_view_name: str,
    derived_inventory: Any | None = None,
    calculated_inventory: Any | None = None,
    segments_inventory: Any | None = None,
    output_format: str = "console",
    output_dir: str | Path = ".",
    quiet: bool = False,
    inventory_order: list[str] | None = None,
) -> dict[str, Any]:
    """
    Display inventory summary statistics without generating full inventory sheets.

    Args:
        data_view_id: The data view ID
        data_view_name: Human-readable data view name
        derived_inventory: DerivedFieldInventory object (optional)
        calculated_inventory: CalculatedMetricsInventory object (optional)
        segments_inventory: SegmentsInventory object (optional)
        output_format: Output format - "console" or "json"
        output_dir: Directory for JSON output
        quiet: Suppress console output
        inventory_order: Order of inventory types as specified in CLI (default: ['segments', 'calculated', 'derived'])

    Returns:
        Dictionary with summary statistics
    """
    summary: dict[str, Any] = {
        "data_view_id": data_view_id,
        "data_view_name": data_view_name,
        "timestamp": datetime.now(UTC).isoformat(),
        "inventories": {},
    }

    high_complexity_items: list[dict[str, Any]] = []

    # Process derived fields inventory
    if derived_inventory:
        derived_summary = derived_inventory.get_summary()
        summary["inventories"]["derived_fields"] = derived_summary

        # Collect high-complexity items (>=70)
        high_complexity_items.extend(
            {
                "type": "Derived Field",
                "name": field.component_name,
                "complexity": field.complexity_score,
                "summary": field.logic_summary[:60] + "..." if len(field.logic_summary) > 60 else field.logic_summary,
            }
            for field in derived_inventory.fields
            if field.complexity_score >= 70
        )

    # Process calculated metrics inventory
    if calculated_inventory:
        calc_summary = calculated_inventory.get_summary()
        summary["inventories"]["calculated_metrics"] = calc_summary

        # Collect high-complexity items (>=70)
        high_complexity_items.extend(
            {
                "type": "Calculated Metric",
                "name": metric.metric_name,
                "complexity": metric.complexity_score,
                "summary": metric.formula_summary[:60] + "..."
                if len(metric.formula_summary) > 60
                else metric.formula_summary,
            }
            for metric in calculated_inventory.metrics
            if metric.complexity_score >= 70
        )

    # Process segments inventory
    if segments_inventory:
        seg_summary = segments_inventory.get_summary()
        summary["inventories"]["segments"] = seg_summary

        # Collect high-complexity items (>=70)
        high_complexity_items.extend(
            {
                "type": "Segment",
                "name": segment.segment_name,
                "complexity": segment.complexity_score,
                "summary": segment.definition_summary[:60] + "..."
                if len(segment.definition_summary) > 60
                else segment.definition_summary,
            }
            for segment in segments_inventory.segments
            if segment.complexity_score >= 70
        )

    # Sort high-complexity items by score descending
    high_complexity_items.sort(key=lambda x: x["complexity"], reverse=True)
    summary["high_complexity_items"] = high_complexity_items

    # Console output
    if not quiet and output_format in ("console", "all"):
        print()
        print(ConsoleColors.bold(f"Inventory Summary: {data_view_name}"))
        print(ConsoleColors.dim(f"Data View ID: {data_view_id}"))
        print()

        # Determine display order (default: segments, calculated, derived)
        display_order = inventory_order or ["segments", "calculated", "derived"]

        # Helper functions for displaying each inventory type
        def display_segments() -> None:
            if "segments" not in summary["inventories"]:
                return
            ss = summary["inventories"]["segments"]
            print(ConsoleColors.cyan("Segments"))
            print(f"  Total:       {ss['total_segments']}")
            gov = ss.get("governance", {})
            if gov:
                print(f"  Approved:    {gov.get('approved_count', 0)}")
                print(f"  Shared:      {gov.get('shared_count', 0)}")
                print(f"  Tagged:      {gov.get('tagged_count', 0)}")
            containers = ss.get("container_types", {})
            if containers:
                container_str = ", ".join(f"{k}: {v}" for k, v in containers.items())
                print(f"  Containers:  {container_str}")
            print(f"  Complexity:  avg={ss['complexity']['average']:.1f}, max={ss['complexity']['max']:.1f}")
            if ss["complexity"]["high_complexity_count"] > 0:
                print(ConsoleColors.warning(f"  High (>=75): {ss['complexity']['high_complexity_count']}"))
            if ss["complexity"]["elevated_complexity_count"] > 0:
                print(ConsoleColors.dim(f"  Elevated (50-74): {ss['complexity']['elevated_complexity_count']}"))
            print()

        def display_calculated() -> None:
            if "calculated_metrics" not in summary["inventories"]:
                return
            cs = summary["inventories"]["calculated_metrics"]
            print(ConsoleColors.cyan("Calculated Metrics"))
            print(f"  Total:       {cs['total_calculated_metrics']}")
            gov = cs.get("governance", {})
            if gov:
                print(f"  Approved:    {gov.get('approved_count', 0)}")
                print(f"  Shared:      {gov.get('shared_count', 0)}")
                print(f"  Tagged:      {gov.get('tagged_count', 0)}")
            print(f"  Complexity:  avg={cs['complexity']['average']:.1f}, max={cs['complexity']['max']:.1f}")
            if cs["complexity"]["high_complexity_count"] > 0:
                print(ConsoleColors.warning(f"  High (>=75): {cs['complexity']['high_complexity_count']}"))
            if cs["complexity"]["elevated_complexity_count"] > 0:
                print(ConsoleColors.dim(f"  Elevated (50-74): {cs['complexity']['elevated_complexity_count']}"))
            print()

        def display_derived() -> None:
            if "derived_fields" not in summary["inventories"]:
                return
            ds = summary["inventories"]["derived_fields"]
            print(ConsoleColors.cyan("Derived Fields"))
            print(f"  Total:       {ds['total_derived_fields']}")
            print(f"  Metrics:     {ds['metrics_count']}")
            print(f"  Dimensions:  {ds['dimensions_count']}")
            print(f"  Complexity:  avg={ds['complexity']['average']:.1f}, max={ds['complexity']['max']:.1f}")
            if ds["complexity"]["high_complexity_count"] > 0:
                print(ConsoleColors.warning(f"  High (>=75): {ds['complexity']['high_complexity_count']}"))
            if ds["complexity"]["elevated_complexity_count"] > 0:
                print(ConsoleColors.dim(f"  Elevated (50-74): {ds['complexity']['elevated_complexity_count']}"))
            print()

        # Display in specified order
        display_funcs = {
            "segments": display_segments,
            "calculated": display_calculated,
            "derived": display_derived,
        }
        for inv_type in display_order:
            if inv_type in display_funcs:
                display_funcs[inv_type]()

        # High complexity warnings
        if high_complexity_items:
            print(ConsoleColors.warning(f"High-Complexity Items ({len(high_complexity_items)}):"))
            for item in high_complexity_items[:10]:  # Show top 10
                complexity = item["complexity"]
                print(f"  {ConsoleColors.bold(f'{complexity:3}')} {item['type']:18} {item['name']}")
                if item["summary"]:
                    print(f"       {ConsoleColors.dim(item['summary'])}")
            if len(high_complexity_items) > 10:
                print(ConsoleColors.dim(f"  ... and {len(high_complexity_items) - 10} more"))
            print()

    # JSON output
    if output_format in ("json", "all"):
        safe_name = re.sub(r"[^\w\-]", "_", data_view_name)[:50]
        json_path = Path(output_dir) / f"{safe_name}_inventory_summary.json"
        write_json_atomic_compatible(
            json_path,
            summary,
            indent=2,
            ensure_ascii=True,
            default=str,
            trailing_newline=False,
        )
        if not quiet:
            print(f"Summary saved to: {json_path}")

    return summary
