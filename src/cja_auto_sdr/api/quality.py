"""Data quality validation for CJA Auto SDR."""

import logging
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, ClassVar, Final

import numpy as np
import pandas as pd
from tqdm import tqdm

from cja_auto_sdr.api.cache import ValidationCache
from cja_auto_sdr.core.colors import _format_error_msg
from cja_auto_sdr.core.constants import DEFAULT_VALIDATION_WORKERS, QUALITY_SEVERITY_ORDER, TQDM_BAR_FORMAT

# Stable, versioned rule identities. A rule's meaning change bumps the ``.vN`` suffix.
QUALITY_RULE_IDS: Final[dict[str, str]] = {
    "Empty Data": "dq.empty_data.v1",
    "Missing Fields": "dq.missing_required_fields.v1",
    "Duplicates": "dq.duplicate_name.v1",
    "Null Values": "dq.null_critical_field.v1",
    "Missing Descriptions": "dq.missing_description.v1",
    "Invalid IDs": "dq.invalid_id.v1",
}
CUSTOM_RULE_ID: Final = "dq.custom.unknown"


def partition_component_ids(values: Iterable[object]) -> tuple[list[str], int]:
    """Split values into sorted unique addressable component IDs and an unaddressable count.

    Unaddressable values are None, pandas NA/NaN, empty or whitespace-only strings,
    booleans, and anything that is not a ``str`` or ``int``. IDs are never derived from names.
    """
    addressable: set[str] = set()
    unaddressable = 0
    for value in values:
        if isinstance(value, str):
            if value.strip():
                addressable.add(value)
            else:
                unaddressable += 1
        elif isinstance(value, (bool, np.bool_)):
            unaddressable += 1
        elif isinstance(value, (int, np.integer)):
            addressable.add(str(int(value)))
        else:
            unaddressable += 1
    return sorted(addressable), unaddressable


def _ids_for_mask(df: pd.DataFrame, mask: Any) -> list[object]:
    """Return raw id values for the masked rows (empty when there is no id column)."""
    if "id" not in df.columns:
        return []
    return df.loc[mask, "id"].tolist()


class DataQualityChecker:
    # Severity levels in priority order (highest to lowest) for proper sorting
    SEVERITY_ORDER: ClassVar[list[str]] = list(QUALITY_SEVERITY_ORDER)

    def __init__(
        self,
        logger: logging.Logger,
        validation_cache: ValidationCache | None = None,
        quiet: bool = False,
        log_high_severity_issues: bool = True,
    ):
        self.issues = []
        self.logger = logger
        self.validation_cache = validation_cache  # Optional cache for performance
        self._issues_lock = threading.Lock()  # Thread safety for parallel validation
        self.quiet = quiet
        self.log_high_severity_issues = log_high_severity_issues

    def add_issue(
        self,
        severity: str,
        category: str,
        item_type: str,
        item_name: str,
        description: str,
        details: str = "",
        *,
        rule_id: str | None = None,
        component_ids: Iterable[object] | None = None,
        occurrences: int | None = None,
    ) -> dict[str, Any]:
        """Add a data quality issue to the tracker (thread-safe)"""
        if component_ids is None:
            ids: list[str] = []
            unaddressable = 0
            default_occurrences = 1
        else:
            values = list(component_ids)
            ids, unaddressable = partition_component_ids(values)
            default_occurrences = len(values)
        if occurrences is None:
            occurrences = default_occurrences
        elif component_ids is not None:
            # Occurrences beyond the supplied values have no usable ID.
            unaddressable += max(0, occurrences - default_occurrences)
        issue = {
            "Severity": severity,
            "Category": category,
            "Type": item_type,
            "Item Name": item_name,
            "Issue": description,
            "Details": details,
            "Rule ID": rule_id if rule_id is not None else QUALITY_RULE_IDS.get(category, CUSTOM_RULE_ID),
            "Component IDs": ids,
            "Occurrences": int(occurrences),
            "Unaddressable IDs": unaddressable,
        }

        # Thread-safe append operation
        with self._issues_lock:
            self.issues.append(issue)

        # Conditional logging based on log level for performance
        # Only log individual issues in DEBUG mode
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("DQ Issue [%s] - %s: %s", severity, item_type, description)
        elif (
            self.log_high_severity_issues
            and severity in ["CRITICAL", "HIGH"]
            and self.logger.isEnabledFor(logging.WARNING)
        ):
            # In non-DEBUG modes, only log CRITICAL/HIGH severity issues
            self.logger.warning("DQ Issue [%s] - %s: %s", severity, item_type, description)
        return issue

    def check_duplicates(self, df: pd.DataFrame, item_type: str):
        """Check for duplicate names in metrics or dimensions"""
        try:
            if df.empty:
                self.logger.info("Skipping duplicate check for empty %s dataframe", item_type)
                return

            if "name" not in df.columns:
                self.logger.warning("'name' column not found in %s. Skipping duplicate check.", item_type)
                return

            duplicates = df["name"].value_counts()
            duplicates = duplicates[duplicates > 1]

            for name, count in duplicates.items():
                self.add_issue(
                    severity="HIGH",
                    category="Duplicates",
                    item_type=item_type,
                    item_name=str(name),
                    description=f"Duplicate name found {count} times",
                    details=f"This {item_type.lower()} name appears {count} times in the data view",
                    component_ids=_ids_for_mask(df, df["name"] == name),
                    occurrences=int(count),
                )
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            self.logger.error(_format_error_msg("checking duplicates", item_type, e))

    def check_required_fields(self, df: pd.DataFrame, item_type: str, required_fields: list[str]):
        """Validate that required fields are present"""
        try:
            if df.empty:
                self.logger.info("Skipping required fields check for empty %s dataframe", item_type)
                return

            missing_fields = [field for field in required_fields if field not in df.columns]

            if missing_fields:
                self.add_issue(
                    severity="CRITICAL",
                    category="Missing Fields",
                    item_type=item_type,
                    item_name="N/A",
                    description="Required fields missing from API response",
                    details=f"Missing fields: {', '.join(missing_fields)}",
                )
        except (TypeError, AttributeError) as e:
            self.logger.error(_format_error_msg("checking required fields", item_type, e))

    def check_null_values(self, df: pd.DataFrame, item_type: str, critical_fields: list[str]):
        """Check for null values in critical fields"""
        try:
            if df.empty:
                self.logger.info("Skipping null value check for empty %s dataframe", item_type)
                return

            for field in critical_fields:
                if field in df.columns:
                    null_mask = df[field].isna()
                    null_count = null_mask.sum()
                    if null_count > 0:
                        null_items = df.loc[null_mask, "name"].tolist() if "name" in df.columns else []
                        item_names = ", ".join(str(x) for x in null_items)
                        self.add_issue(
                            severity="MEDIUM",
                            category="Null Values",
                            item_type=item_type,
                            item_name=item_names,
                            description=f'Null values in "{field}" field',
                            details=f"{null_count} item(s) missing {field}. Items: {item_names}",
                            component_ids=_ids_for_mask(df, null_mask),
                            occurrences=int(null_count),
                        )
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            self.logger.error(_format_error_msg("checking null values", item_type, e))

    def check_missing_descriptions(self, df: pd.DataFrame, item_type: str):
        """Check for items without descriptions"""
        try:
            if df.empty:
                self.logger.info("Skipping description check for empty %s dataframe", item_type)
                return

            if "description" not in df.columns:
                self.logger.info("'description' column not found in %s", item_type)
                return

            missing_desc = df["description"].isna() | (df["description"] == "")
            missing_desc_count = missing_desc.sum()
            if missing_desc_count > 0:
                item_names = df.loc[missing_desc, "name"].tolist() if "name" in df.columns else []
                self.add_issue(
                    severity="LOW",
                    category="Missing Descriptions",
                    item_type=item_type,
                    item_name=f"{missing_desc_count} items",
                    description=f"{missing_desc_count} items without descriptions",
                    details=f"Items: {', '.join(str(x) for x in item_names)}",
                    component_ids=_ids_for_mask(df, missing_desc),
                    occurrences=int(missing_desc_count),
                )
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            self.logger.error(_format_error_msg("checking descriptions", item_type, e))

    def check_empty_dataframe(self, df: pd.DataFrame, item_type: str):
        """Check if dataframe is empty"""
        try:
            if df.empty:
                self.add_issue(
                    severity="CRITICAL",
                    category="Empty Data",
                    item_type=item_type,
                    item_name="N/A",
                    description=f"No {item_type.lower()} found in data view",
                    details=f"The API returned an empty dataset for {item_type.lower()}",
                )
        except (AttributeError, TypeError) as e:
            self.logger.error(_format_error_msg("checking if dataframe is empty", item_type, e))

    def check_id_validity(self, df: pd.DataFrame, item_type: str):
        """Check for missing or invalid IDs"""
        try:
            if df.empty:
                self.logger.info("Skipping ID validity check for empty %s dataframe", item_type)
                return

            if "id" not in df.columns:
                self.logger.warning("'id' column not found in %s", item_type)
                return

            missing_ids_count = (df["id"].isna() | (df["id"] == "")).sum()
            if missing_ids_count > 0:
                self.add_issue(
                    severity="HIGH",
                    category="Invalid IDs",
                    item_type=item_type,
                    item_name=f"{missing_ids_count} items",
                    description=f"{missing_ids_count} items with missing or invalid IDs",
                    details="Items without valid IDs may cause issues in reporting",
                    component_ids=[],
                    occurrences=int(missing_ids_count),
                )
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            self.logger.error(_format_error_msg("checking ID validity", item_type, e))

    def check_all_quality_issues_optimized(
        self,
        df: pd.DataFrame,
        item_type: str,
        required_fields: list[str],
        critical_fields: list[str],
    ):
        """
        Combine vectorized checks, exiting early for empty data or missing required fields.

        Optional caching reuses validation results. Masks and column selection
        avoid materializing full rows when only counts or names are needed.
        """
        try:
            # Check cache first (before any processing)
            cache_key = None
            local_issues: list[dict[str, Any]] = []

            def _record_issue(
                severity: str,
                category: str,
                item_name: str,
                description: str,
                details: str = "",
                component_ids: Iterable[object] | None = None,
                occurrences: int | None = None,
            ) -> None:
                issue = self.add_issue(
                    severity=severity,
                    category=category,
                    item_type=item_type,
                    item_name=item_name,
                    description=description,
                    details=details,
                    component_ids=component_ids,
                    occurrences=occurrences,
                )
                # Keep a per-call copy so cache writes cannot bleed across concurrent threads.
                local_issues.append({**issue, "Component IDs": list(issue["Component IDs"])})

            if self.validation_cache is not None:
                cached_issues, cache_key = self.validation_cache.get(df, item_type, required_fields, critical_fields)
                if cached_issues is not None:
                    with self._issues_lock:
                        self.issues.extend(cached_issues)
                    self.logger.debug("Using cached validation results for %s", item_type)
                    return

            # Check 1: Empty DataFrame (quick exit)
            if df.empty:
                _record_issue(
                    severity="CRITICAL",
                    category="Empty Data",
                    item_name="N/A",
                    description=f"No {item_type.lower()} found in data view",
                    details=f"The API returned an empty dataset for {item_type.lower()}",
                )
                if self.validation_cache is not None:
                    self.validation_cache.put(df, item_type, required_fields, critical_fields, local_issues, cache_key)
                return

            # Check 2: Required fields validation
            missing_fields = [field for field in required_fields if field not in df.columns]
            if missing_fields:
                _record_issue(
                    severity="CRITICAL",
                    category="Missing Fields",
                    item_name="N/A",
                    description="Required fields missing from API response",
                    details=f"Missing fields: {', '.join(missing_fields)}",
                )
                if self.validation_cache is not None:
                    self.validation_cache.put(df, item_type, required_fields, critical_fields, local_issues, cache_key)
                return

            # Check 3: Vectorized duplicate detection
            if "name" in df.columns:
                duplicates = df["name"].value_counts()
                duplicates = duplicates[duplicates > 1]
                ids_by_name = (
                    df[df["name"].isin(duplicates.index)].groupby("name", sort=False)["id"].agg(list)
                    if len(duplicates) and "id" in df.columns
                    else None
                )
                for name, count in duplicates.items():
                    _record_issue(
                        severity="HIGH",
                        category="Duplicates",
                        item_name=str(name),
                        description=f"Duplicate name found {count} times",
                        details=f"This {item_type.lower()} name appears {count} times in the data view",
                        component_ids=ids_by_name.loc[name] if ids_by_name is not None else [],
                        occurrences=int(count),
                    )

            # Check 4: Vectorized null value checks
            available_critical_fields = [f for f in critical_fields if f in df.columns]
            if available_critical_fields:
                # Reuse one isna() mask for counts and item-name lookups instead
                # of re-scanning each flagged column.
                null_mask = df[available_critical_fields].isna()
                null_counts = null_mask.sum()
                has_name_column = "name" in df.columns
                for field, null_count in null_counts[null_counts > 0].items():
                    null_items = df.loc[null_mask[field], "name"].tolist() if has_name_column else []
                    item_names = ", ".join(str(x) for x in null_items)
                    _record_issue(
                        severity="MEDIUM",
                        category="Null Values",
                        item_name=item_names,
                        description=f'Null values in "{field}" field',
                        details=f"{null_count} item(s) missing {field}. Items: {item_names}",
                        component_ids=_ids_for_mask(df, null_mask[field]),
                        occurrences=int(null_count),
                    )

            # Check 5: Vectorized missing descriptions check
            if "description" in df.columns:
                missing_desc = df["description"].isna() | (df["description"] == "")
                missing_desc_count = missing_desc.sum()
                if missing_desc_count > 0:
                    item_names = df.loc[missing_desc, "name"].tolist() if "name" in df.columns else []
                    _record_issue(
                        severity="LOW",
                        category="Missing Descriptions",
                        item_name=f"{missing_desc_count} items",
                        description=f"{missing_desc_count} items without descriptions",
                        details=f"Items: {', '.join(str(x) for x in item_names)}",
                        component_ids=_ids_for_mask(df, missing_desc),
                        occurrences=int(missing_desc_count),
                    )

            # Check 6: Vectorized ID validity check
            if "id" in df.columns:
                missing_ids_count = (df["id"].isna() | (df["id"] == "")).sum()
                if missing_ids_count > 0:
                    _record_issue(
                        severity="HIGH",
                        category="Invalid IDs",
                        item_name=f"{missing_ids_count} items",
                        description=f"{missing_ids_count} items with missing or invalid IDs",
                        details="Items without valid IDs may cause issues in reporting",
                        component_ids=[],
                        occurrences=int(missing_ids_count),
                    )

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("Optimized validation complete for %s: %s items checked", item_type, len(df))

            if self.validation_cache is not None:
                self.validation_cache.put(df, item_type, required_fields, critical_fields, local_issues, cache_key)

        except Exception as e:  # Intentional: Orchestrator boundary for optimized single-pass validation
            self.logger.error(_format_error_msg("in optimized validation", item_type, e))
            self.logger.exception("Full error details:")
            raise

    def check_all_parallel(
        self,
        metrics_df: pd.DataFrame,
        dimensions_df: pd.DataFrame,
        metrics_required_fields: list[str],
        dimensions_required_fields: list[str],
        critical_fields: list[str],
        max_workers: int = DEFAULT_VALIDATION_WORKERS,
    ):
        """
        Run validation checks in parallel for metrics and dimensions
        """
        try:
            self.logger.info("Starting parallel validation (metrics and dimensions)")

            tasks = {
                "metrics": lambda: self.check_all_quality_issues_optimized(
                    metrics_df,
                    "Metrics",
                    metrics_required_fields,
                    critical_fields,
                ),
                "dimensions": lambda: self.check_all_quality_issues_optimized(
                    dimensions_df,
                    "Dimensions",
                    dimensions_required_fields,
                    critical_fields,
                ),
            }

            failures: list[tuple[str, Exception]] = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_name = {executor.submit(task): name for name, task in tasks.items()}

                with tqdm(
                    total=len(tasks),
                    desc="Validating data",
                    unit="check",
                    bar_format=TQDM_BAR_FORMAT,
                    leave=False,
                    disable=self.quiet,
                ) as pbar:
                    for future in as_completed(future_to_name):
                        task_name = future_to_name[future]
                        try:
                            future.result()
                            pbar.set_postfix_str(f"\u2713 {task_name}", refresh=True)
                            self.logger.debug("\u2713 %s validation completed", task_name.capitalize())
                        except Exception as e:  # Intentional: Future result collection must handle any worker exception
                            failures.append((task_name, e))
                            pbar.set_postfix_str(f"\u2717 {task_name}", refresh=True)
                            self.logger.error("\u2717 %s validation failed: %s", task_name.capitalize(), e)
                            self.logger.exception("Full error details:")
                        pbar.update(1)

            if failures:
                details = "; ".join(f"{name}: {error}" for name, error in failures)
                raise RuntimeError(f"Data quality validation workers failed: {details}") from failures[0][1]

            self.logger.info("Parallel validation complete. Found %s issue(s)", len(self.issues))

        except Exception as e:  # Intentional: Parallel executor boundary; thread pool can surface heterogeneous errors
            self.logger.error(_format_error_msg("in parallel validation", error=e))
            self.logger.exception("Full error details:")
            raise

    def get_issues_dataframe(self, max_issues: int = 0) -> pd.DataFrame:
        """Return all issues as a DataFrame sorted by severity (CRITICAL first)

        Args:
            max_issues: Maximum number of issues to return (0 = all issues)
        """
        try:
            if not self.issues:
                self.logger.info("No data quality issues found")
                return pd.DataFrame(
                    {
                        "Severity": ["INFO"],
                        "Category": ["Data Quality"],
                        "Type": ["All"],
                        "Item Name": ["N/A"],
                        "Issue": ["No data quality issues detected"],
                        "Details": ["All validation checks passed successfully"],
                        "Rule ID": [None],
                        "Component IDs": [[]],
                        "Occurrences": [0],
                        "Unaddressable IDs": [0],
                    },
                )

            df = pd.DataFrame(self.issues)

            # Use CategoricalDtype for proper severity ordering (CRITICAL > HIGH > MEDIUM > LOW > INFO)
            severity_dtype = pd.CategoricalDtype(categories=self.SEVERITY_ORDER, ordered=True)
            df["Severity"] = df["Severity"].astype(severity_dtype)

            # Reorder columns: Severity first for better readability
            preferred_order = [
                "Severity",
                "Category",
                "Type",
                "Item Name",
                "Issue",
                "Details",
                "Rule ID",
                "Component IDs",
                "Occurrences",
                "Unaddressable IDs",
            ]
            existing_cols = [col for col in preferred_order if col in df.columns]
            other_cols = [col for col in df.columns if col not in preferred_order]
            df = df[existing_cols + other_cols]

            # Sort by severity then by Category alphabetically
            df = df.sort_values(by=["Severity", "Category"], ascending=[True, True])

            # Limit to top N issues if max_issues > 0
            if max_issues > 0 and len(df) > max_issues:
                self.logger.info("Limiting data quality issues to top %s (of %s total)", max_issues, len(df))
                df = df.head(max_issues)

            return df
        except (
            Exception
        ) as e:  # Intentional: DataFrame construction from heterogeneous issue dicts can fail in many ways
            self.logger.error(_format_error_msg("creating issues dataframe", error=e))
            return pd.DataFrame(
                {
                    "Severity": ["ERROR"],
                    "Category": ["System"],
                    "Type": ["Processing"],
                    "Item Name": ["N/A"],
                    "Issue": ["Error generating data quality report"],
                    "Details": [str(e)],
                    "Rule ID": [None],
                    "Component IDs": [[]],
                    "Occurrences": [0],
                    "Unaddressable IDs": [0],
                },
            )

    def log_summary(self):
        """Log aggregated summary of data quality issues for performance"""
        if not self.issues:
            self.logger.info("\u2713 No data quality issues found")
            return

        # Aggregate by severity
        severity_counts: dict[str, int] = {}
        for issue in self.issues:
            sev = issue["Severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        self.logger.info("Data quality validation complete: %s issue(s) found", len(self.issues))

        if self.logger.isEnabledFor(logging.INFO):
            for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if sev in severity_counts:
                    self.logger.info("  %s: %s", sev, severity_counts[sev])
        elif self.logger.isEnabledFor(logging.WARNING):
            # Minimal warning-level telemetry for production mode.
            high_severity = {
                sev: count for sev, count in severity_counts.items() if sev in ("CRITICAL", "HIGH") and count > 0
            }
            if high_severity:
                details = ", ".join(f"{sev}: {count}" for sev, count in high_severity.items())
                self.logger.warning("Data quality high-severity summary: %s", details)
