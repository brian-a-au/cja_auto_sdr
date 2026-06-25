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
    "cja_auto_sdr.output.notion_org_publisher.find_existing_row_id",
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
    patches["cja_auto_sdr.output.notion_org_publisher.ensure_database"].return_value = ("db-123", "ds-123")
    patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"].return_value = "row-id"
    patches["cja_auto_sdr.output.notion_org_publisher.find_existing_row_id"].return_value = None
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
        first_call = upsert.call_args_list[0]
        second_call = upsert.call_args_list[1]
        assert first_call.kwargs["properties"]["Name"]["title"][0]["text"]["content"] == "DV One"
        assert second_call.kwargs["properties"]["Name"]["title"][0]["text"]["content"] == "DV Two"
        # Verify data_source_id is threaded through
        assert first_call.kwargs["data_source_id"] == "ds-123"
        assert second_call.kwargs["data_source_id"] == "ds-123"
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


def test_ensure_database_notion_api_error_raises_notion_api_error():
    """ensure_database Notion API error → NotionAPIError (not raw API error traceback)."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion
        from cja_auto_sdr.output.writers.notion import NotionAPIError

        # Simulate a Notion APIResponseError from databases.retrieve on bad id
        class FakeAPIResponseError(Exception):
            def __init__(self):
                super().__init__("object_not_found")
                self.code = "object_not_found"

        FakeAPIResponseError.__name__ = "APIResponseError"
        FakeAPIResponseError.__qualname__ = "APIResponseError"

        patches["cja_auto_sdr.output.notion_org_publisher.ensure_database"].side_effect = FakeAPIResponseError()

        org_report = _make_org_report([])
        logger = MagicMock()

        with pytest.raises(NotionAPIError):
            publish_org_report_catalog_to_notion(
                org_report,
                output_dir="/tmp/test_out",
                logger=logger,
                database_id="bad-id",
                create_database=False,
            )
    finally:
        patch.stopall()


def test_existing_database_does_not_require_parent_page():
    """With a database_id set, the catalog upserts rows and must NOT require a parent page."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        org_report = _make_org_report([_make_summary("dv_001", "DV One")])
        publish_org_report_catalog_to_notion(
            org_report,
            output_dir="/tmp/test_out",
            logger=MagicMock(),
            database_id="db-123",
            create_database=False,
        )
        resolve = patches["cja_auto_sdr.output.notion_org_publisher.resolve_notion_credentials"]
        assert resolve.call_args.kwargs.get("require_parent") is False
    finally:
        patch.stopall()


def test_bootstrap_requires_parent_page():
    """Creating a new database (no id) still requires the parent page."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        org_report = _make_org_report([_make_summary("dv_001", "DV One")])
        publish_org_report_catalog_to_notion(
            org_report,
            output_dir="/tmp/test_out",
            logger=MagicMock(),
            database_id=None,
            create_database=True,
        )
        resolve = patches["cja_auto_sdr.output.notion_org_publisher.resolve_notion_credentials"]
        assert resolve.call_args.kwargs.get("require_parent") is True
    finally:
        patch.stopall()


def test_ensure_database_unexpected_error_reraises():
    """A non-API, non-ValueError error from ensure_database propagates unchanged."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        patches["cja_auto_sdr.output.notion_org_publisher.ensure_database"].side_effect = RuntimeError("disk full")

        org_report = _make_org_report([])
        with pytest.raises(RuntimeError, match="disk full"):
            publish_org_report_catalog_to_notion(
                org_report,
                output_dir="/tmp/test_out",
                logger=MagicMock(),
                database_id="db-123",
                create_database=False,
            )
    finally:
        patch.stopall()


def test_row_failure_non_api_error_reraises_when_not_continue_on_error():
    """A non-API upsert failure with continue_on_error=False propagates unchanged."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion

        patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"].side_effect = RuntimeError("boom")

        org_report = _make_org_report([_make_summary("dv_001", "DV One")])
        with pytest.raises(RuntimeError, match="boom"):
            publish_org_report_catalog_to_notion(
                org_report,
                output_dir="/tmp/test_out",
                logger=MagicMock(),
                database_id="db-123",
                create_database=False,
            )
    finally:
        patch.stopall()


def test_row_failure_api_error_raises_notion_api_error_when_not_continue_on_error():
    """A Notion API upsert failure with continue_on_error=False → NotionAPIError."""
    patches = _apply_base_patches()
    try:
        from cja_auto_sdr.output.notion_org_publisher import publish_org_report_catalog_to_notion
        from cja_auto_sdr.output.writers.notion import NotionAPIError

        class FakeAPIResponseError(Exception):
            def __init__(self):
                super().__init__("conflict_error")
                self.code = "conflict_error"

        FakeAPIResponseError.__name__ = "APIResponseError"
        FakeAPIResponseError.__qualname__ = "APIResponseError"

        patches["cja_auto_sdr.output.notion_org_publisher.upsert_database_row"].side_effect = FakeAPIResponseError()

        org_report = _make_org_report([_make_summary("dv_001", "DV One")])
        with pytest.raises(NotionAPIError):
            publish_org_report_catalog_to_notion(
                org_report,
                output_dir="/tmp/test_out",
                logger=MagicMock(),
                database_id="db-123",
                create_database=False,
            )
    finally:
        patch.stopall()


def test_adapter_forwards_continue_on_error():
    """write_org_report_notion must forward continue_on_error to the publisher."""
    from cja_auto_sdr.org.writers.notion import write_org_report_notion

    with patch("cja_auto_sdr.output.notion_org_publisher.publish_org_report_catalog_to_notion") as pub:
        pub.return_value = []
        write_org_report_notion(
            MagicMock(),
            "/tmp/out",
            MagicMock(),
            notion_database_id="db-1",
            continue_on_error=True,
        )
        assert pub.call_args.kwargs["continue_on_error"] is True
