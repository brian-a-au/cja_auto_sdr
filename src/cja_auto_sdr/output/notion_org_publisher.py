"""Publish org-report summary catalog to the Notion SDR Registry database."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.output.notion_database import (
    build_catalog_row_properties,
    ensure_database,
    find_existing_row_id,
    upsert_database_row,
)
from cja_auto_sdr.output.notion_registry import (
    get_registry_path,
    lookup_database_row_id,
    lookup_page_id,
    store_database_row_id,
)
from cja_auto_sdr.output.writers.notion import (
    NotionAPIError,
    NotionConfigurationError,
    _build_client,
    _friendly_notion_error_message,
    _is_notion_api_error,
    _require_notion_client,
    resolve_notion_credentials,
)

__all__ = ["publish_org_report_catalog_to_notion"]


def publish_org_report_catalog_to_notion(
    org_report: Any,
    *,
    output_dir: str | Path,
    logger: logging.Logger,
    database_id: str | None,
    create_database: bool,
    force_new: bool = False,  # noqa: ARG001 — accepted for signature parity; not used
    continue_on_error: bool = False,
) -> list[str]:
    token, parent_page_id = resolve_notion_credentials()
    Client = _require_notion_client()
    client = _build_client(Client, token)

    registry_path = get_registry_path(output_dir)

    try:
        db_id, ds_id = ensure_database(
            client,
            parent_page_id=parent_page_id,
            database_id=database_id,
            create_if_missing=create_database,
        )
    except ValueError as exc:
        raise NotionConfigurationError(str(exc)) from exc
    except Exception as exc:
        if _is_notion_api_error(exc):
            raise NotionAPIError(_friendly_notion_error_message(exc)) from exc
        raise
    if database_id is None and create_database:
        # Surface the bootstrapped database ID so it can be captured/automated.
        logger.info("✓ Created Notion SDR Registry database: %s", db_id)
        logger.info(
            "  Reuse it with --notion-database-id %s (or set NOTION_DATABASE_ID).",
            db_id,
        )

    cataloged: list[str] = []
    for summary in org_report.data_view_summaries:
        dv_id = summary.data_view_id
        if summary.has_error:
            logger.warning(
                "Skipping errored data view %s: %s",
                dv_id,
                summary.normalized_error_reason,
            )
            continue

        try:
            page_id = lookup_page_id(registry_path, dv_id)
            props = build_catalog_row_properties(
                data_view_name=summary.data_view_name,
                data_view_id=dv_id,
                metrics_count=summary.metric_count,
                dimensions_count=summary.dimension_count,
                page_id=page_id,
                tool_version=__version__,
                captured_at=org_report.timestamp,
            )
            existing_row_id = lookup_database_row_id(registry_path, dv_id)
            if existing_row_id is None:
                existing_row_id = find_existing_row_id(
                    client,
                    data_source_id=ds_id,
                    data_view_id=dv_id,
                )
            row_id = upsert_database_row(
                client,
                data_source_id=ds_id,
                existing_row_id=existing_row_id,
                properties=props,
            )
            store_database_row_id(registry_path, dv_id, row_id)
            cataloged.append(dv_id)
        except Exception as exc:
            if continue_on_error:
                logger.warning("Failed to catalog data view %s: %s", dv_id, exc)
                continue
            if _is_notion_api_error(exc):
                raise NotionAPIError(_friendly_notion_error_message(exc)) from exc
            raise

    return cataloged
