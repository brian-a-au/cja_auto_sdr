"""Stats and name-resolution helpers extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import json
import logging
from typing import Any

import cjapy

__all__ = [
    "_build_inspection_name_resolution_logger",
    "_build_name_resolution_result",
    "_coerce_name_resolution_result",
    "_collect_stats_row",
    "_collect_stats_row_with_fallback",
    "_require_numeric_component_count_for_stats",
    "_stats_error_row",
    "resolve_data_view_names",
    "show_stats",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def _build_name_resolution_result(
    resolved_ids: list[str],
    name_to_ids_map: dict[str, list[str]],
    diagnostics: Any,
    *,
    include_diagnostics: bool,
):
    """Return either legacy 2-tuple or extended 3-tuple name-resolution output."""
    if include_diagnostics:
        return resolved_ids, name_to_ids_map, diagnostics
    return resolved_ids, name_to_ids_map


def _coerce_name_resolution_result(result):
    """Normalize name-resolution return values into a diagnostics-bearing tuple."""
    generator = _generator_module()
    if len(result) == 2:
        resolved_ids, name_to_ids_map = result
        return resolved_ids, name_to_ids_map, generator.NameResolutionDiagnostics()
    resolved_ids, name_to_ids_map, diagnostics = result
    if isinstance(diagnostics, generator.NameResolutionDiagnostics):
        return resolved_ids, name_to_ids_map, diagnostics
    return resolved_ids, name_to_ids_map, generator.NameResolutionDiagnostics()


def _build_inspection_name_resolution_logger() -> logging.Logger:
    """Create a muted logger for inspection resolution to keep stderr machine-safe."""
    logger = logging.getLogger("name_resolution.inspection")
    logger.setLevel(logging.CRITICAL + 1)
    logger.propagate = False
    if not any(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
        logger.addHandler(logging.NullHandler())
    return logger


def resolve_data_view_names(
    identifiers: list[str],
    config_file: str = "config.json",
    logger: logging.Logger | None = None,
    suggest_similar: bool = True,
    profile: str | None = None,
    match_mode: str = "exact",
    include_diagnostics: bool = False,
):
    """Resolve data view names to IDs while preserving legacy return contracts."""
    generator = _generator_module()

    if logger is None:
        logger = logging.getLogger(__name__)
    resolution_diagnostics = generator.NameResolutionDiagnostics()

    match_mode = (match_mode or "exact").strip().lower()
    if match_mode not in {"exact", "insensitive", "fuzzy"}:
        raise ValueError(f"Invalid match_mode: {match_mode}")

    resolved_ids = []
    name_to_ids_map = {}
    unresolved_names: list[str] = []

    try:
        logger.info(f"Resolving data view identifiers: {identifiers}")
        success, source, credentials = generator.configure_cjapy(profile, config_file, logger)
        if not success:
            error_message = f"Failed to configure credentials: {source}"
            logger.error(error_message)
            resolution_diagnostics = generator.NameResolutionDiagnostics(
                error_type="configuration_error",
                error_message=error_message,
            )
            return _build_name_resolution_result(
                [],
                {},
                resolution_diagnostics,
                include_diagnostics=include_diagnostics,
            )
        cja = generator.cjapy.CJA()

        logger.debug("Fetching all data views for name resolution")
        cache_key = generator._build_data_view_cache_key(
            config_file=config_file,
            credential_source=source,
            credentials=credentials,
            profile=profile,
        )
        available_dvs = generator.get_cached_data_views(cja, cache_key, logger)

        if not available_dvs:
            error_message = "No data views found or no access to any data views"
            logger.error(error_message)
            resolution_diagnostics = generator.NameResolutionDiagnostics(
                error_type="configuration_error",
                error_message=error_message,
            )
            return _build_name_resolution_result(
                [],
                {},
                resolution_diagnostics,
                include_diagnostics=include_diagnostics,
            )

        name_to_id_lookup: dict[str, list[str]] = {}
        name_to_id_lookup_ci: dict[str, list[str]] = {}
        id_to_name_lookup: dict[str, str] = {}

        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = dv.get("id")
                dv_name = dv.get("name")
                if dv_id and dv_name:
                    id_to_name_lookup[dv_id] = dv_name
                    name_to_id_lookup.setdefault(dv_name, []).append(dv_id)
                    name_to_id_lookup_ci.setdefault(dv_name.lower(), []).append(dv_id)

        logger.debug(
            "Built lookup map with %s unique names and %s IDs",
            len(name_to_id_lookup),
            len(id_to_name_lookup),
        )

        for identifier in identifiers:
            if generator.is_data_view_id(identifier):
                if identifier in id_to_name_lookup:
                    resolved_ids.append(identifier)
                    logger.debug("ID '%s' validated: %s", identifier, id_to_name_lookup[identifier])
                else:
                    logger.warning("Data view ID '%s' not found in accessible data views", identifier)
                    resolved_ids.append(identifier)
                continue

            matching_ids: list[str] | None = None
            if match_mode == "exact":
                matching_ids = name_to_id_lookup.get(identifier)
            elif match_mode == "insensitive":
                matching_ids = name_to_id_lookup_ci.get(identifier.lower())
            elif match_mode == "fuzzy":
                matching_ids = name_to_id_lookup.get(identifier) or name_to_id_lookup_ci.get(identifier.lower())
                if matching_ids is None:
                    similar = generator.find_similar_names(
                        identifier, list(name_to_id_lookup.keys()), max_suggestions=1
                    )
                    if similar:
                        best_name, best_distance = similar[0]
                        matching_ids = name_to_id_lookup.get(best_name)
                        logger.warning(
                            "Name '%s' fuzzy-matched to '%s' (distance: %s)",
                            identifier,
                            best_name,
                            best_distance,
                        )

            if matching_ids:
                resolved_ids.extend(matching_ids)
                name_to_ids_map[identifier] = matching_ids
                if len(matching_ids) == 1:
                    logger.info("Name '%s' resolved to ID: %s", identifier, matching_ids[0])
                else:
                    logger.info("Name '%s' matched %s data views: %s", identifier, len(matching_ids), matching_ids)
                continue

            logger.error("Data view name '%s' not found in accessible data views", identifier)
            unresolved_names.append(identifier)

            if suggest_similar:
                similar = generator.find_similar_names(identifier, list(name_to_id_lookup.keys()))
                if similar:
                    case_match = [s for s in similar if s[1] == 0]
                    if case_match:
                        logger.error("  → Did you mean '%s'? (case mismatch)", case_match[0][0])
                    else:
                        suggestions = [f"'{s[0]}'" for s in similar]
                        logger.error("  → Did you mean: %s?", ", ".join(suggestions))

            if match_mode == "exact":
                logger.error("  → Name matching is CASE-SENSITIVE and requires EXACT match")
            elif match_mode == "insensitive":
                logger.error("  → Name matching is case-insensitive exact match")
            else:
                logger.error("  → Name matching uses fuzzy nearest-match mode")
            logger.error("  → Run 'cja_auto_sdr --list-dataviews' to see all available names")

        if not resolved_ids and unresolved_names:
            unresolved_label = unresolved_names[0]
            resolved_name_by_id = {
                resolved_id: id_to_name_lookup[resolved_id]
                for resolved_id in resolved_ids
                if resolved_id in id_to_name_lookup
            }
            resolution_diagnostics = generator.NameResolutionDiagnostics(
                error_type="not_found",
                error_message=(
                    f"Could not resolve data view: '{unresolved_label}'. "
                    "Run 'cja_auto_sdr --list-dataviews' to see available names and IDs."
                ),
                resolved_name_by_id=resolved_name_by_id,
            )
        else:
            resolution_diagnostics = generator.NameResolutionDiagnostics(
                resolved_name_by_id={
                    resolved_id: id_to_name_lookup[resolved_id]
                    for resolved_id in resolved_ids
                    if resolved_id in id_to_name_lookup
                }
            )

        logger.info("Resolved %s identifier(s) to %s data view ID(s)", len(identifiers), len(resolved_ids))
        return _build_name_resolution_result(
            resolved_ids,
            name_to_ids_map,
            resolution_diagnostics,
            include_diagnostics=include_diagnostics,
        )
    except FileNotFoundError:
        error_message = f"Configuration file '{config_file}' not found"
        logger.error(error_message)
        resolution_diagnostics = generator.NameResolutionDiagnostics(
            error_type="configuration_error",
            error_message=error_message,
        )
        return _build_name_resolution_result(
            [],
            {},
            resolution_diagnostics,
            include_diagnostics=include_diagnostics,
        )
    except generator.RECOVERABLE_CONFIG_API_EXCEPTIONS as e:
        error_message = f"Failed to resolve data view names: {e!s}"
        logger.error(error_message)
        resolution_diagnostics = generator.NameResolutionDiagnostics(
            error_type="connectivity_error",
            error_message=error_message,
        )
        return _build_name_resolution_result(
            [],
            {},
            resolution_diagnostics,
            include_diagnostics=include_diagnostics,
        )
    except (AttributeError, RuntimeError) as e:
        error_message = f"Failed to resolve data view names (unexpected): {e!s}"
        logger.error(error_message)
        logger.debug("Unexpected error during name resolution", exc_info=True)
        resolution_diagnostics = generator.NameResolutionDiagnostics(
            error_type="connectivity_error",
            error_message=error_message,
        )
        return _build_name_resolution_result(
            [],
            {},
            resolution_diagnostics,
            include_diagnostics=include_diagnostics,
        )


def _stats_error_row(data_view_id: str, error: Exception) -> dict[str, Any]:
    """Build a consistent non-fatal stats error row for one data view."""
    return {
        "id": data_view_id,
        "name": "ERROR",
        "owner": "N/A",
        "metrics": 0,
        "dimensions": 0,
        "total_components": 0,
        "description": f"Error: {error!s}",
    }


def _require_numeric_component_count_for_stats(
    cja: cjapy.CJA,
    data_view_id: str,
    *,
    fetch_spec: Any,
    component_label: str,
) -> int:
    """Return a strict numeric component count for stats rows or raise for invalid payloads."""
    generator = _generator_module()
    count = generator._count_component_items_for_fetch_spec(cja, data_view_id, fetch_spec)
    if isinstance(count, int):
        return count
    raise ValueError(f"Failed to retrieve {component_label} for data view '{data_view_id}'")


def _collect_stats_row(cja: cjapy.CJA, data_view_id: str) -> dict[str, Any]:
    """Fetch one data view's stats row. Raises on API/runtime errors."""
    generator = _generator_module()
    raw_dv_info = generator._fetch_dataview_lookup_payload(cja, data_view_id)
    dv_info, lookup_failure_reason, _ = generator._coerce_valid_dataview_lookup_payload(
        raw_dv_info,
        data_view_id=data_view_id,
        require_expected_id=False,
    )
    if dv_info is None:
        raise ValueError(f"Data view validation failed for '{data_view_id}' ({lookup_failure_reason})")

    metrics_count = _require_numeric_component_count_for_stats(
        cja,
        data_view_id,
        fetch_spec=generator._METRICS_COMPONENT_FETCH_SPEC,
        component_label="metrics",
    )
    dimensions_count = _require_numeric_component_count_for_stats(
        cja,
        data_view_id,
        fetch_spec=generator._DIMENSIONS_COMPONENT_FETCH_SPEC,
        component_label="dimensions",
    )

    description_text = generator._normalize_optional_text(dv_info.get("description"), default="")
    return {
        "id": data_view_id,
        "name": dv_info.get("name", "Unknown"),
        "owner": dv_info.get("owner", {}).get("name", "N/A") if isinstance(dv_info.get("owner"), dict) else "N/A",
        "metrics": metrics_count,
        "dimensions": dimensions_count,
        "total_components": metrics_count + dimensions_count,
        "description": description_text[:100] + "..." if len(description_text) > 100 else description_text,
    }


def _collect_stats_row_with_fallback(cja: cjapy.CJA, data_view_id: str, logger: logging.Logger) -> dict[str, Any]:
    """Return one stats row, converting non-fatal per-item failures into an ERROR row."""
    generator = _generator_module()
    try:
        return _collect_stats_row(cja, data_view_id)
    except generator.RECOVERABLE_STATS_ROW_EXCEPTIONS as e:
        logger.debug("Failed to collect stats row for %s", data_view_id, exc_info=True)
        return _stats_error_row(data_view_id, e)


def show_stats(
    data_views: list[str],
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    quiet: bool = False,
    profile: str | None = None,
) -> bool:
    """Show quick statistics about data view(s) without generating full reports."""
    generator = _generator_module()
    is_stdout = output_file in ("-", "stdout")
    is_machine_readable = generator._is_machine_readable_output(output_format, output_file)

    if not is_machine_readable and not quiet:
        print()
        print("=" * generator.BANNER_WIDTH)
        print("DATA VIEW STATISTICS")
        print("=" * generator.BANNER_WIDTH)
        if profile:
            print(f"\nUsing profile: {profile}")
        print()

    try:
        success, source, _ = generator.configure_cjapy(profile, config_file)
        if not success:
            generator._emit_discovery_error(
                f"Configuration error: {source}",
                is_machine_readable=is_machine_readable,
                error_type="configuration_error",
                human_to_stderr=False,
            )
            return False

        cja = generator.cjapy.CJA()
        logger = logging.getLogger(__name__)
        stats_data = [_collect_stats_row_with_fallback(cja, dv_id, logger) for dv_id in data_views]

        if output_format == "json" or (is_stdout and output_format != "csv"):
            output_data = json.dumps(
                {
                    "stats": stats_data,
                    "count": len(stats_data),
                    "totals": {
                        "metrics": sum(s["metrics"] for s in stats_data),
                        "dimensions": sum(s["dimensions"] for s in stats_data),
                        "components": sum(s["total_components"] for s in stats_data),
                    },
                },
                indent=2,
                allow_nan=False,
            )
            if is_stdout or not output_file:
                print(output_data)
            else:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(output_data)
        elif output_format == "csv":
            lines = ["id,name,owner,metrics,dimensions,total_components"]
            for item in stats_data:
                name = item["name"].replace('"', '""')
                owner = item["owner"].replace('"', '""')
                lines.append(
                    f'{item["id"]},"{name}","{owner}",{item["metrics"]},{item["dimensions"]},{item["total_components"]}'
                )
            output_data = "\n".join(lines)
            if is_stdout or not output_file:
                print(output_data)
            else:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(output_data)
        else:
            if stats_data:
                max_id_width = max(len("ID"), *(len(s["id"]) for s in stats_data)) + 2
                max_name_width = min(40, max(len("Name"), *(len(s["name"]) for s in stats_data)) + 2)
                header = (
                    f"{'ID':<{max_id_width}} {'Name':<{max_name_width}} {'Metrics':>8} {'Dimensions':>10} {'Total':>8}"
                )
                print(header)
                print("-" * len(header))
                for item in stats_data:
                    name = (
                        item["name"][: max_name_width - 2] + ".."
                        if len(item["name"]) > max_name_width - 2
                        else item["name"]
                    )
                    print(
                        f"{item['id']:<{max_id_width}} {name:<{max_name_width}} {item['metrics']:>8} {item['dimensions']:>10} {item['total_components']:>8}"
                    )
                print("-" * len(header))
                total_metrics = sum(s["metrics"] for s in stats_data)
                total_dims = sum(s["dimensions"] for s in stats_data)
                total_all = sum(s["total_components"] for s in stats_data)
                print(
                    f"{'TOTAL':<{max_id_width}} {'':<{max_name_width}} {total_metrics:>8} {total_dims:>10} {total_all:>8}"
                )

            print()
            print("=" * generator.BANNER_WIDTH)

        return True
    except FileNotFoundError:
        generator._emit_discovery_error(
            f"Configuration file '{config_file}' not found",
            is_machine_readable=is_machine_readable,
            error_type="configuration_error",
            human_to_stderr=False,
        )
        return False
    except KeyboardInterrupt, SystemExit:
        if not is_machine_readable:
            print()
            print(generator.ConsoleColors.warning("Operation cancelled."))
        raise
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        generator._emit_discovery_error(
            f"Failed to get stats: {e!s}",
            is_machine_readable=is_machine_readable,
            error_type="connectivity_error",
            human_to_stderr=False,
        )
        return False
