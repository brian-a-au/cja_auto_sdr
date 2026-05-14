"""Pytest configuration and fixtures for CJA SDR Generator tests"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from cja_auto_sdr.org.models import (
    ComponentDistribution,
    ComponentInfo,
    DataViewCluster,
    DataViewSummary,
    OrgReportConfig,
    OrgReportResult,
    SimilarityPair,
)
from tests.category_rules import auto_test_markers_for_file


@pytest.fixture(autouse=True)
def clear_fast_path_option_spec_cache():
    """Reset fast-path CLI option cache between tests for isolation."""
    from cja_auto_sdr.__main__ import _fast_path_option_spec

    _fast_path_option_spec.cache_clear()
    yield
    _fast_path_option_spec.cache_clear()


@pytest.fixture(autouse=True)
def reset_watch_module_state():
    """Reset module-level mutable state in cja_auto_sdr.cli.commands.watch.

    In-process watch tests touch `_stop_requested`, `_stop_reason_holder`, and
    `_previous_handlers` directly. Without this teardown a test that exits before
    `run_watch`'s own `finally` runs (e.g. an assertion failure mid-call) would
    leave the watch SIGINT/SIGTERM handler installed for the rest of the session.
    Cheap no-op for the vast majority of tests that don't import the watch module.
    """
    yield

    watch_mod = sys.modules.get("cja_auto_sdr.cli.commands.watch")
    if watch_mod is None:
        return
    watch_mod._stop_requested.clear()
    watch_mod._stop_reason_holder.clear()
    if watch_mod._previous_handlers:
        watch_mod._restore_signal_handlers()


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Auto-classify tests so marker-based selection stays maintainable.

    The suite is currently organized primarily by file naming rather than by
    nested unit/integration directories. Apply stable markers centrally so CI
    and local development can target fast unit runs, smoke checks, and broader
    integration coverage without requiring per-test boilerplate.
    """
    del config  # Hook signature requires config even though classification is static.

    for item in items:
        module_name = Path(str(item.fspath)).name
        existing_markers = {marker.name for marker in item.iter_markers()}
        auto_markers = auto_test_markers_for_file(module_name)

        for marker_name in auto_markers:
            if marker_name not in existing_markers:
                item.add_marker(getattr(pytest.mark, marker_name))
                existing_markers.add(marker_name)


@pytest.fixture
def rich_org_report_result():
    """Create a comprehensive org report result used by renderer and CLI tests."""
    config = OrgReportConfig(
        core_threshold=0.5,
        include_metadata=True,
        overlap_threshold=0.95,
        summary_only=False,
        include_component_types=True,
        include_drift=True,
    )

    summaries = [
        DataViewSummary(
            data_view_id="dv_001",
            data_view_name="Primary Business Data View With A Long Name",
            metric_ids={"metric/core/1", "metric/common/1", "metric/limited/1"},
            dimension_ids={"dimension/core/1", "dimension/common/1"},
            metric_count=3,
            dimension_count=2,
            standard_metric_count=2,
            derived_metric_count=1,
            standard_dimension_count=1,
            derived_dimension_count=1,
            owner="Alice",
            owner_id="owner_1",
            created="2026-01-01T00:00:00+00:00",
            modified="2026-02-15T10:00:00+00:00",
            has_description=True,
        ),
        DataViewSummary(
            data_view_id="dv_002",
            data_view_name="Secondary Data View",
            metric_count=0,
            dimension_count=0,
            error="permission denied",
            status="error",
        ),
        DataViewSummary(
            data_view_id="dv_003",
            data_view_name="Tertiary Data View",
            metric_ids={"metric/core/2", "metric/isolated/1"},
            dimension_ids={"dimension/isolated/1"},
            metric_count=2,
            dimension_count=1,
            standard_metric_count=1,
            derived_metric_count=1,
            standard_dimension_count=1,
            derived_dimension_count=0,
            owner="Carol",
            owner_id="owner_3",
            created="2026-01-03T00:00:00+00:00",
            modified="2026-02-15T11:00:00+00:00",
        ),
    ]

    distribution = ComponentDistribution(
        core_metrics=["metric/core/1", "metric/core/2"],
        core_dimensions=["dimension/core/1"],
        common_metrics=["metric/common/1"],
        common_dimensions=["dimension/common/1"],
        limited_metrics=["metric/limited/1"],
        limited_dimensions=["dimension/limited/1"],
        isolated_metrics=["metric/isolated/1"],
        isolated_dimensions=["dimension/isolated/1"],
    )

    component_index = {
        "metric/core/1": ComponentInfo(
            component_id="metric/core/1",
            component_type="metric",
            name="Core Metric One",
            data_views={"dv_001", "dv_003"},
        ),
        "metric/core/2": ComponentInfo(
            component_id="metric/core/2",
            component_type="metric",
            name="Core Metric Two",
            data_views={"dv_001", "dv_003"},
        ),
        "metric/common/1": ComponentInfo(
            component_id="metric/common/1",
            component_type="metric",
            name="Common Metric",
            data_views={"dv_001", "dv_002"},
        ),
        "metric/limited/1": ComponentInfo(
            component_id="metric/limited/1",
            component_type="metric",
            name="Limited Metric",
            data_views={"dv_001", "dv_002"},
        ),
        "metric/isolated/1": ComponentInfo(
            component_id="metric/isolated/1",
            component_type="metric",
            name="Isolated Metric",
            data_views={"dv_003"},
        ),
        "dimension/core/1": ComponentInfo(
            component_id="dimension/core/1",
            component_type="dimension",
            name="Core Dimension",
            data_views={"dv_001", "dv_003"},
        ),
        "dimension/common/1": ComponentInfo(
            component_id="dimension/common/1",
            component_type="dimension",
            name="Common Dimension",
            data_views={"dv_001", "dv_002"},
        ),
        "dimension/limited/1": ComponentInfo(
            component_id="dimension/limited/1",
            component_type="dimension",
            name="Limited Dimension",
            data_views={"dv_001", "dv_002"},
        ),
        "dimension/isolated/1": ComponentInfo(
            component_id="dimension/isolated/1",
            component_type="dimension",
            name="Isolated Dimension",
            data_views={"dv_003"},
        ),
    }

    similarity_pairs = [
        SimilarityPair(
            dv1_id="dv_001",
            dv1_name="Primary Business Data View With A Very Long Name",
            dv2_id="dv_003",
            dv2_name="Tertiary Data View Also Quite Long",
            jaccard_similarity=0.93,
            shared_count=15,
            union_count=18,
            only_in_dv1=["metric/limited/1", "dimension/common/1", "metric/common/1", "metric/x"],
            only_in_dv2=["metric/isolated/1", "dimension/isolated/1", "dimension/y", "metric/z"],
            only_in_dv1_names={
                "metric/limited/1": "Limited Metric",
                "dimension/common/1": "Common Dimension",
            },
            only_in_dv2_names={
                "metric/isolated/1": "Isolated Metric",
                "dimension/isolated/1": "Isolated Dimension",
            },
        ),
    ]
    similarity_pairs.extend(
        [
            SimilarityPair(
                dv1_id=f"dv_{i:03d}",
                dv1_name=f"Data View {i}",
                dv2_id=f"dv_{i + 1:03d}",
                dv2_name=f"Data View {i + 1}",
                jaccard_similarity=0.90,
                shared_count=20,
                union_count=22,
            )
            for i in range(10, 31)
        ],
    )

    clusters = [
        DataViewCluster(
            cluster_id=i,
            cluster_name=f"Cluster {i}",
            data_view_ids=[f"dv_{i:03d}", f"dv_{i + 100:03d}", f"dv_{i + 200:03d}", f"dv_{i + 300:03d}"],
            data_view_names=[
                f"Data View {i}",
                f"Data View {i + 100}",
                f"Data View {i + 200}",
                f"Data View {i + 300}",
            ],
            cohesion_score=0.78,
        )
        for i in range(1, 12)
    ]

    owner_data = {
        f"Owner {i}": {
            "data_view_count": i,
            "total_metrics": i * 10,
            "total_dimensions": i * 5,
            "avg_components_per_dv": float(i * 3),
        }
        for i in range(1, 18)
    }

    stale_components = [
        {"pattern": "deprecated_prefix", "name": f"old_metric_{i}", "component_id": f"metric/old/{i}"} for i in range(6)
    ]
    stale_components.extend(
        [
            {"pattern": "legacy_suffix", "name": f"segment_{i}_old", "component_id": f"segment/old/{i}"}
            for i in range(3)
        ],
    )

    recommendations = [
        {
            "severity": "high",
            "reason": "A data view has many isolated components",
            "data_view": "dv_001",
            "data_view_name": "Primary Business Data View",
        },
        {
            "severity": "medium",
            "reason": "Two data views are highly similar",
            "data_view_1": "dv_001",
            "data_view_1_name": "Primary Business Data View",
            "data_view_2": "dv_003",
            "data_view_2_name": "Tertiary Data View",
        },
    ]

    return OrgReportResult(
        timestamp="2026-02-16T12:00:00+00:00",
        org_id="test_org@AdobeOrg",
        parameters=config,
        data_view_summaries=summaries,
        component_index=component_index,
        distribution=distribution,
        similarity_pairs=similarity_pairs,
        recommendations=recommendations,
        duration=12.34,
        clusters=clusters,
        is_sampled=True,
        total_available_data_views=25,
        governance_violations=[
            {"message": "Duplicate threshold exceeded", "threshold": 5, "actual": 11},
        ],
        naming_audit={
            "case_styles": {"snake_case": 9, "camelCase": 4, "UPPER_CASE": 2},
            "total_components": 15,
            "recommendations": [{"severity": "medium", "message": "Prefer snake_case for new components"}],
        },
        owner_summary={
            "by_owner": owner_data,
            "owners_sorted_by_dv_count": list(owner_data.keys()),
        },
        stale_components=stale_components,
    )


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary mock configuration file"""
    config_data = {
        "org_id": "test_org@AdobeOrg",
        "client_id": "test_client_id",
        "secret": "test_secret",
        "scopes": "openid, AdobeID, additional_info.projectedProductContext",
    }
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)


@pytest.fixture
def mock_cja_instance():
    """Create a mock CJA instance"""
    mock_cja = Mock()

    # Mock data views
    mock_cja.getDataViews.return_value = [
        {"id": "dv_test_12345", "name": "Test Data View 1"},
        {"id": "dv_test_67890", "name": "Test Data View 2"},
    ]

    # Mock single data view
    mock_cja.getDataView.return_value = {
        "id": "dv_test_12345",
        "name": "Test Data View 1",
        "owner": {"name": "Test Owner"},
    }

    # Mock metrics
    mock_cja.getMetrics.return_value = [
        {
            "id": "metric1",
            "name": "Test Metric 1",
            "type": "calculated",
            "title": "Test Metric 1 Title",
            "description": "Test metric description",
        },
        {
            "id": "metric2",
            "name": "Test Metric 2",
            "type": "standard",
            "title": "Test Metric 2 Title",
            "description": None,  # Missing description for testing
        },
    ]

    # Mock dimensions
    mock_cja.getDimensions.return_value = [
        {
            "id": "dim1",
            "name": "Test Dimension 1",
            "type": "string",
            "title": "Test Dimension 1 Title",
            "description": "Test dimension description",
        },
        {
            "id": "dim2",
            "name": "Test Dimension 2",
            "type": "string",
            "title": "Test Dimension 2 Title",
            "description": "",
        },
        {
            "id": "dim3",
            "name": "Test Dimension 1",  # Duplicate name for testing
            "type": "string",
            "title": "Test Dimension Duplicate",
            "description": "Duplicate dimension",
        },
    ]

    return mock_cja


@pytest.fixture
def sample_metrics_df():
    """Create a sample metrics DataFrame for testing"""
    return pd.DataFrame(
        [
            {
                "id": "metric1",
                "name": "Test Metric 1",
                "type": "calculated",
                "title": "Test Metric 1 Title",
                "description": "Test metric description",
            },
            {
                "id": "metric2",
                "name": "Test Metric 2",
                "type": "standard",
                "title": "Test Metric 2 Title",
                "description": None,
            },
        ],
    )


@pytest.fixture
def sample_dimensions_df():
    """Create a sample dimensions DataFrame for testing"""
    return pd.DataFrame(
        [
            {
                "id": "dim1",
                "name": "Test Dimension 1",
                "type": "string",
                "title": "Test Dimension 1 Title",
                "description": "Test dimension description",
            },
            {
                "id": "dim2",
                "name": "Test Dimension 2",
                "type": "string",
                "title": "Test Dimension 2 Title",
                "description": "",
            },
            {
                "id": "dim3",
                "name": "Test Dimension 1",  # Duplicate
                "type": "string",
                "title": "Test Dimension Duplicate",
                "description": "Duplicate dimension",
            },
        ],
    )


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def large_sample_dataframe():
    """Create a large sample DataFrame for performance testing"""
    size = 500  # Large enough to show performance differences
    return pd.DataFrame(
        {
            "id": [f"id_{i}" for i in range(size)],
            "name": [f"Name {i}" if i % 10 != 0 else f"Name {i % 50}" for i in range(size)],  # Some duplicates
            "type": ["metric" if i % 2 == 0 else "calculated" for i in range(size)],
            "description": [f"Description {i}" if i % 3 != 0 else None for i in range(size)],  # Some nulls
            "title": [f"Title {i}" for i in range(size)],
        },
    )


@pytest.fixture
def sample_data_dict(sample_metrics_df, sample_dimensions_df):
    """Create a sample data dictionary for output format testing"""
    return {
        "Metadata": pd.DataFrame(
            {
                "Property": ["Generated At", "Data View ID", "Tool Version"],
                "Value": ["2024-01-01 12:00:00", "dv_test_12345", "3.0"],
            },
        ),
        "Data Quality": pd.DataFrame(
            [
                {
                    "Severity": "HIGH",
                    "Category": "Duplicates",
                    "Type": "Dimensions",
                    "Item Name": "Test Dimension 1",
                    "Issue": "Duplicate name found 2 times",
                    "Details": "This dimension appears multiple times",
                },
            ],
        ),
        "DataView Details": pd.DataFrame(
            {"Property": ["Name", "ID", "Owner"], "Value": ["Test Data View 1", "dv_test_12345", "Test Owner"]},
        ),
        "Metrics": sample_metrics_df,
        "Dimensions": sample_dimensions_df,
    }


@pytest.fixture
def sample_metadata_dict():
    """Create a sample metadata dictionary for output format testing"""
    return {
        "Generated At": "2024-01-01 12:00:00",
        "Data View ID": "dv_test_12345",
        "Data View Name": "Test Data View 1",
        "Tool Version": "3.0",
        "Metrics Count": "2",
        "Dimensions Count": "3",
    }


@pytest.fixture
def large_metrics_df():
    """Generate large metrics DataFrame for performance testing"""
    data = []
    for i in range(1000):
        data.append(
            {
                "id": f"metric_{i}",
                "name": f"Test Metric {i}",
                "type": "calculated",
                "title": f"Metric {i}",
                "description": f"Description {i}" if i % 2 == 0 else "",  # Some missing
            },
        )
    return pd.DataFrame(data)


@pytest.fixture
def large_dimensions_df():
    """Generate large dimensions DataFrame for performance testing"""
    data = []
    for i in range(1000):
        data.append(
            {
                "id": f"dimension_{i}",
                "name": f"Test Dimension {i}",
                "type": "string",
                "title": f"Dimension {i}",
                "description": f"Description {i}" if i % 3 == 0 else "",  # Some missing
            },
        )
    return pd.DataFrame(data)


@pytest.fixture
def mock_env_credentials():
    """Create mock OAuth environment credentials"""
    return {
        "ORG_ID": "test_org@AdobeOrg",
        "CLIENT_ID": "test_client_id",
        "SECRET": "test_secret",
        "SCOPES": "openid, AdobeID, additional_info.projectedProductContext",
    }


@pytest.fixture
def clean_env():
    """Fixture to temporarily clear credential environment variables"""
    # Save current env vars
    saved = {}
    credential_vars = ["ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "SANDBOX", "CJA_PROFILE", "CJA_HOME"]
    for k in credential_vars:
        if k in os.environ:
            saved[k] = os.environ.pop(k)

    yield

    # Restore env vars
    for k, v in saved.items():
        os.environ[k] = v


@pytest.fixture
def mock_profile_credentials():
    """Create mock profile credentials"""
    return {
        "org_id": "profile_org@AdobeOrg",
        "client_id": "profile_client_id_12345678",
        "secret": "profile_secret_12345678",
        "scopes": "openid, AdobeID, additional_info.projectedProductContext",
    }


@pytest.fixture
def temp_profiles_dir(tmp_path):
    """Create a temporary profiles directory with test profiles"""
    profiles_dir = tmp_path / ".cja" / "orgs"
    profiles_dir.mkdir(parents=True)

    # Create client-a profile with config.json
    client_a = profiles_dir / "client-a"
    client_a.mkdir()
    config_a = {
        "org_id": "clienta@AdobeOrg",
        "client_id": "client_a_id_12345678",
        "secret": "client_a_secret_12345678",
        "scopes": "openid",
    }
    (client_a / "config.json").write_text(json.dumps(config_a))

    # Create client-b profile with .env
    client_b = profiles_dir / "client-b"
    client_b.mkdir()
    env_content = """
ORG_ID=clientb@AdobeOrg
CLIENT_ID=client_b_id_12345678
SECRET=client_b_secret_12345678
SCOPES=openid
"""
    (client_b / ".env").write_text(env_content)

    # Create mixed profile with both config.json and .env
    mixed = profiles_dir / "mixed"
    mixed.mkdir()
    config_mixed = {
        "org_id": "mixed_json@AdobeOrg",
        "client_id": "mixed_client_id",
        "secret": "mixed_secret",
        "scopes": "openid",
    }
    (mixed / "config.json").write_text(json.dumps(config_mixed))
    (mixed / ".env").write_text("ORG_ID=mixed_env@AdobeOrg")  # Override org_id

    return tmp_path / ".cja"


@pytest.fixture
def clean_profile_env():
    """Fixture to temporarily clear profile-related environment variables"""
    saved = {}
    profile_vars = ["CJA_PROFILE", "CJA_HOME"]
    for k in profile_vars:
        if k in os.environ:
            saved[k] = os.environ.pop(k)

    yield

    for k, v in saved.items():
        os.environ[k] = v


# ==================== DERIVED FIELD ANALYSIS FIXTURES ====================


@pytest.fixture
def sample_derived_metric():
    """Create a sample derived metric definition"""
    return {
        "id": "metrics/bounces",
        "name": "Bounces",
        "description": "Session bounce count",
        "sourceFieldType": "derived",
        "type": "int",
        "fieldDefinition": json.dumps(
            [
                {"func": "raw-field", "id": "adobe_sessionstarts", "label": "starts"},
                {"func": "raw-field", "id": "adobe_sessionends", "label": "ends"},
                {
                    "func": "match",
                    "field": "starts",
                    "branches": [
                        {
                            "pred": {
                                "func": "and",
                                "preds": [{"func": "isset", "field": "starts"}, {"func": "isset", "field": "ends"}],
                            },
                            "map-to": 1,
                        },
                        {"pred": {"func": "true"}, "map-to": 0},
                    ],
                    "#rule_name": "Bounces",
                    "#rule_type": "caseWhen",
                },
            ],
        ),
        "dataSetType": "event",
    }


@pytest.fixture
def sample_derived_dimension():
    """Create a sample derived dimension definition"""
    return {
        "id": "dimensions/marketing_channel",
        "name": "Marketing Channel",
        "description": "Traffic source classification",
        "sourceFieldType": "derived",
        "type": "string",
        "fieldDefinition": json.dumps(
            [
                {"func": "raw-field", "id": "web.referringDomain", "label": "referrer"},
                {
                    "func": "match",
                    "field": "referrer",
                    "branches": [
                        {
                            "pred": {"func": "contains", "field": "referrer", "value": "google"},
                            "map-to": "Organic Search",
                        },
                        {"pred": {"func": "contains", "field": "referrer", "value": "facebook"}, "map-to": "Social"},
                        {"pred": {"func": "true"}, "map-to": "Direct"},
                    ],
                    "#rule_name": "Channel Classification",
                },
            ],
        ),
        "dataSetType": "event",
    }


@pytest.fixture
def sample_derived_metrics_df(sample_derived_metric):
    """Create a DataFrame with derived metrics"""
    return pd.DataFrame(
        [
            sample_derived_metric,
            {
                "id": "metrics/visitors",
                "name": "People",
                "description": "Unique visitors",
                "sourceFieldType": "standard",
                "type": "int",
                "fieldDefinition": None,
                "dataSetType": "event",
            },
        ],
    )


@pytest.fixture
def sample_derived_dimensions_df(sample_derived_dimension):
    """Create a DataFrame with derived dimensions"""
    return pd.DataFrame(
        [
            sample_derived_dimension,
            {
                "id": "dimensions/page",
                "name": "Page Name",
                "description": "Page path",
                "sourceFieldType": "custom",
                "type": "string",
                "fieldDefinition": None,
                "dataSetType": "event",
            },
        ],
    )


# ==================== CALCULATED METRICS INVENTORY FIXTURES ====================


@pytest.fixture
def sample_simple_calculated_metric():
    """Create a simple calculated metric definition (Revenue per Order)"""
    return {
        "id": "cm_revenue_per_order",
        "name": "Revenue per Order",
        "description": "Average revenue per order",
        "owner": {"name": "Test Owner"},
        "polarity": "positive",
        "type": "currency",
        "precision": 2,
        "definition": {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {
                "func": "divide",
                "col1": {"func": "metric", "name": "metrics/revenue"},
                "col2": {"func": "metric", "name": "metrics/orders"},
            },
        },
    }


@pytest.fixture
def sample_complex_calculated_metric():
    """Create a complex calculated metric with segment filter"""
    return {
        "id": "cm_mobile_conversion",
        "name": "Mobile Conversion Rate",
        "description": "Conversion rate for mobile visitors",
        "owner": {"name": "Analytics Team"},
        "polarity": "positive",
        "type": "percent",
        "precision": 2,
        "definition": {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {
                "func": "segment",
                "segment_id": "s_mobile_visitors",
                "metric": {
                    "func": "divide",
                    "col1": {"func": "metric", "name": "metrics/orders"},
                    "col2": {"func": "metric", "name": "metrics/visits"},
                },
            },
        },
    }


@pytest.fixture
def mock_cja_with_calculated_metrics(sample_simple_calculated_metric, sample_complex_calculated_metric):
    """Create a mock CJA instance that returns calculated metrics"""
    mock_cja = Mock()

    # Return calculated metrics as a DataFrame
    mock_cja.getCalculatedMetrics.return_value = pd.DataFrame(
        [sample_simple_calculated_metric, sample_complex_calculated_metric],
    )

    return mock_cja


@pytest.fixture
def mock_cja_with_no_calculated_metrics():
    """Create a mock CJA instance with no calculated metrics"""
    mock_cja = Mock()
    mock_cja.getCalculatedMetrics.return_value = pd.DataFrame()
    return mock_cja
