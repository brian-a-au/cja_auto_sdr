"""Tests for publish_org_report_catalog_to_notion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_summary(dv_id, dv_name, metric_count=5, dimension_count=3, has_error=False):
    s = MagicMock()
    s.data_view_id = dv_id
    s.data_view_name = dv_name
    s.metric_count = metric_count
    s.dimension_count = dimension_count
    s.has_error = has_error
    s.normalized_error_reason = "some error" if has_error else None
    return s


def _make_org_report(summaries, timestamp="2026-06-19T00:00:00Z"):
    r = MagicMock()
    r.data_view_summaries = summaries
    r.timestamp = timestamp
    return r


BASE_PATCHES = [
    "cja_auto_sdr.output.notion_org_publisher.resolve_notion_credentials",
    "cja_auto_sdr.output.notion_org_publisher._require_notion_client",
    "cja_auto_sdr.output.notion_org_publisher.ensure_database",
    "cja_auto_sdr.output.notion_org_publisher.upsert_database_row",
    "cja_auto_sdr.output.notion_org_publisher.lookup_page_id",
    "cja_auto_sdr.output.notion_org_publisher.lookup_database_row_id",
    "cja_auto_sdr.output.notion_org_publisher.store_database_row_id",
]


def _apply_base_patches():
    patches = {}
    for p in BASE_PATCHES:
        m = patch(p)
        patches[p] = m.start()
    patches["cja_auto_sdr.output.notion_org_publisher.resolve_notion_credentials"].return_value = ("token", "parent-id")
    patches["cja_auto_sdr.output.notion_org_publisher._require_notion_client"].return_value = MagicMock(
        return_value=MagicMock()
    )
    patches["cja_auto_sdr.output.notion_org_publisher.ensure_database"].return_value = "db-123"
    patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"].return_value = "row-id"
    patches["cja_auto_sdr.output.notion_org_publisher.lookup_page_id"].return_value = None
    patches["cja_auto_sdr.output.notion_org_publisher.lookup_database_row_id"].return_value = None
    return patches


def test_serial_iteration_two_good_summaries():
    """Two good summaries → upsert called twice in order; returns both dv_ids."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        s1 = _make_summary("dv_001", "DV One")
        s2 = _make_summary("dv_002", "DV Two")
        org_report = _make_org_report([s1, s2])
        logger = MagicMock()

        result = publish_org_report_catalog_to_notion(
            org_report,
            output_dir="/tmp/test_out",
            logger=logger,
            database_id="db-123",
            create_database=False,
        )

        assert result == ["dv_001", "dv_002"]
        upsert = patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"]
        assert upsert.call_count == 2
        # Verify order: first call for dv_001, second for dv_002
        first_props = upsert.call_args_list[0].kwargs["properties"]
        second_props = upsert.call_args_list[1].kwargs["properties"]
        assert first_props["Name"]["title"][0]["text"]["content"] == "DV One"
        assert second_props["Name"]["title"][0]["text"]["content"] == "DV Two"
    finally:
        patch.stopall()


def test_catalog_row_shape():
    """Catalog row has correct counts and empty/unknown for unmeasured columns."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        # page_id returned → SDR Page should contain page url
        patches["cja_auto_sdr.output.notion_org_publisher.lookup_page_id"].return_value = "page-xyz"

        s = _make_summary("dv_001", "DV One", metric_count=10, dimension_count=7)
        org_report = _make_org_report([s])
        logger = MagicMock()

        publish_org_report_catalog_to_notion(
            org_report,
            output_dir="/tmp/test_out",
            logger=logger,
            database_id="db-123",
            create_database=False,
        )

        upsert = patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"]
        props = upsert.call_args.kwargs["properties"]

        assert props["Metrics Count"] == {"number": 10}
        assert props["Dimensions Count"] == {"number": 7}
        assert props["Segments Count"] == {"number": None}
        assert props["Calculated Metrics Count"] == {"number": None}
        assert props["Derived Fields Count"] == {"number": None}
        assert props["Data Quality"] == {"select": {"name": "unknown"}}
        # SDR Page includes the page id
        assert "page-xyz" in props["SDR Page"]["rich_text"][0]["text"]["content"]
        # Currency and Timezone empty
        assert props["Currency"]["rich_text"][0]["text"]["content"] == ""
        assert props["Timezone"]["rich_text"][0]["text"]["content"] == ""
    finally:
        patch.stopall()


def test_catalog_row_shape_no_page_id():
    """SDR Page is empty string when lookup_page_id returns None."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        patches["cja_auto_sdr.output.notion_org_publisher.lookup_page_id"].return_value = None

        s = _make_summary("dv_001", "DV One")
        org_report = _make_org_report([s])
        logger = MagicMock()

        publish_org_report_catalog_to_notion(
            org_report,
            output_dir="/tmp/test_out",
            logger=logger,
            database_id="db-123",
            create_database=False,
        )

        upsert = patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"]
        props = upsert.call_args.kwargs["properties"]
        assert props["SDR Page"]["rich_text"][0]["text"]["content"] == ""
    finally:
        patch.stopall()


def test_continue_on_error_skips_failed_summaries():
    """With continue_on_error=True, failed upsert is skipped; success still returns."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        s1 = _make_summary("dv_001", "DV One")
        s2 = _make_summary("dv_002", "DV Two")
        org_report = _make_org_report([s1, s2])
        logger = MagicMock()

        # First call fails, second succeeds
        upsert = patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"]
        upsert.side_effect = [RuntimeError("boom"), "row-id-2"]

        result = publish_org_report_catalog_to_notion(
            org_report,
            output_dir="/tmp/test_out",
            logger=logger,
            database_id="db-123",
            create_database=False,
            continue_on_error=True,
        )

        assert result == ["dv_002"]
        logger.warning.assert_called()
    finally:
        patch.stopall()


def test_skips_errored_summaries():
    """Summaries with has_error=True are skipped without calling upsert."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        s1 = _make_summary("dv_err", "DV Error", has_error=True)
        s2 = _make_summary("dv_ok", "DV OK")
        org_report = _make_org_report([s1, s2])
        logger = MagicMock()

        result = publish_org_report_catalog_to_notion(
            org_report,
            output_dir="/tmp/test_out",
            logger=logger,
            database_id="db-123",
            create_database=False,
        )

        assert result == ["dv_ok"]
        upsert = patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"]
        assert upsert.call_count == 1
        logger.warning.assert_called()
    finally:
        patch.stopall()


def test_ensure_database_value_error_raises_notion_config_error():
    """ensure_database ValueError → NotionConfigurationError (not raw ValueError)."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion
        from cja_auto_sdr.output.writers.notion import NotionConfigurationError

        patches["cja_auto_sdr.output.notion_org_publisher.ensure_database"].side_effect = ValueError("no db id")

        org_report = _make_org_report([])
        logger = MagicMock()

        with pytest.raises(NotionConfigurationError, match="no db id"):
            publish_org_report_catalog_to_notion(
                org_report,
                output_dir="/tmp/test_out",
                logger=logger,
                database_id=None,
                create_database=False,
            )
    finally:
        patch.stopall()
