"""Org-report Notion writer adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cja_auto_sdr.org.models import OrgReportResult

__all__ = ["write_org_report_notion"]


def write_org_report_notion(
    org_report: OrgReportResult,
    output_dir: Any,
    logger: Any,
    *,
    notion_database_id: str | None = None,
    notion_create_database: bool = False,
    notion_force_new: bool = False,
    continue_on_error: bool = False,
    **_unused: Any,
) -> list[str]:
    from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

    return publish_org_report_catalog_to_notion(
        org_report,
        output_dir=output_dir,
        logger=logger,
        database_id=notion_database_id,
        create_database=notion_create_database,
        force_new=notion_force_new,
        continue_on_error=continue_on_error,
    )
