"""Compare the checked-out Jaccard helper with its version at a trusted local git ref.

Run with PYTHONHASHSEED=0; see docs/performance/pairwise-jaccard.md for commands.
Only the selected method is loaded from git; imports and fixtures are shared.
"""

import argparse
import ast
import gc
import json
import logging
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from time import perf_counter_ns

from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.models import DataViewSummary, OrgReportConfig


def load_baseline(ref):
    source = subprocess.run(
        ["git", "show", f"{ref}:src/cja_auto_sdr/org/analyzer.py"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    cls = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "OrgComponentAnalyzer"
    )
    method = next(node for node in cls.body if getattr(node, "name", None) == "_compute_pairwise_jaccard")
    namespace = {"DataViewSummary": DataViewSummary}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "<git baseline>", "exec"), namespace)  # noqa: S102
    return namespace[method.name]


def make_summaries(views, components):
    # Half shared and half view-specific IDs, split evenly into metrics/dimensions.
    return [
        DataViewSummary(
            data_view_id=f"dv_{view}",
            data_view_name=f"View {view}",
            metric_ids={f"m_{'shared' if i % 2 else view}_{i}" for i in range(components // 2)},
            dimension_ids={f"d_{'shared' if i % 2 else view}_{i}" for i in range(components // 2)},
        )
        for view in range(views)
    ]


def measure(function, analyzer, summaries, loops):
    start = perf_counter_ns()
    for _ in range(loops):
        function(analyzer, summaries)
    return (perf_counter_ns() - start) / loops / 1_000  # microseconds per call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True, help="Trusted local revision containing the original method")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--samples", type=int, default=31)
    parser.add_argument("--warmups", type=int, default=5)
    args = parser.parse_args()
    if args.samples < 2 or args.warmups < 1:
        parser.error("Use at least two samples and one warmup")
    if os.environ.get("PYTHONHASHSEED") != "0":
        parser.error("Run with PYTHONHASHSEED=0 for reproducible set layouts")
    analyzer = OrgComponentAnalyzer(None, OrgReportConfig(), logging.getLogger("benchmark"))
    functions = {"original": load_baseline(args.baseline_ref)}
    if not args.baseline_only:
        functions["modified"] = OrgComponentAnalyzer._compute_pairwise_jaccard
    report = {
        "python": sys.version,
        "platform": platform.platform(),
        "baseline_ref": args.baseline_ref,
        "hash_seed": 0,
        "gc_enabled": gc.isenabled(),
        "samples": args.samples,
        "warmups": args.warmups,
        "cases": [],
    }
    for views, components, loops in [(0, 0, 2000), (3, 20, 1000), (5, 2000, 20), (25, 2000, 2), (5, 10000, 2)]:
        summaries = make_summaries(views, components)
        expected = functions["original"](analyzer, summaries)
        for function in functions.values():
            assert function(analyzer, summaries) == expected
            for _ in range(args.warmups):
                measure(function, analyzer, summaries, loops)
        timings = {name: [] for name in functions}
        for sample in range(args.samples):
            # Alternate execution order to reduce systematic drift bias.
            order = list(functions) if sample % 2 else list(reversed(functions))
            for name in order:
                timings[name].append(measure(functions[name], analyzer, summaries, loops))
        case = {"views": views, "components_per_view": components, "loops_per_sample": loops, "timings_us": {}}
        for name, values in timings.items():
            quartiles = statistics.quantiles(values, n=4)
            case["timings_us"][name] = {
                "median": statistics.median(values),
                "q1": quartiles[0],
                "q3": quartiles[2],
                "min": min(values),
                "max": max(values),
                "samples": values,
            }
        if "modified" in timings:
            original = statistics.median(timings["original"])
            modified = statistics.median(timings["modified"])
            case["saved_us"] = original - modified
            case["reduction_percent"] = 100 * (original - modified) / original
        report["cases"].append(case)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
