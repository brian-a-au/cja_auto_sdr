"""Pytest configuration and fixtures for CJA SDR Generator tests"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock
import pandas as pd


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary mock configuration file"""
    config_data = {
        "org_id": "test_org@AdobeOrg",
        "client_id": "test_client_id",
        "tech_id": "test_tech_id@techacct.adobe.com",
        "secret": "test_secret",
        "private_key": "test_private.key"
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
        {"id": "dv_test_67890", "name": "Test Data View 2"}
    ]

    # Mock single data view
    mock_cja.getDataView.return_value = {
        "id": "dv_test_12345",
        "name": "Test Data View 1",
        "owner": {"name": "Test Owner"}
    }

    # Mock metrics
    mock_cja.getMetrics.return_value = [
        {
            "id": "metric1",
            "name": "Test Metric 1",
            "type": "calculated",
            "title": "Test Metric 1 Title",
            "description": "Test metric description"
        },
        {
            "id": "metric2",
            "name": "Test Metric 2",
            "type": "standard",
            "title": "Test Metric 2 Title",
            "description": None  # Missing description for testing
        }
    ]

    # Mock dimensions
    mock_cja.getDimensions.return_value = [
        {
            "id": "dim1",
            "name": "Test Dimension 1",
            "type": "string",
            "title": "Test Dimension 1 Title",
            "description": "Test dimension description"
        },
        {
            "id": "dim2",
            "name": "Test Dimension 2",
            "type": "string",
            "title": "Test Dimension 2 Title",
            "description": ""
        },
        {
            "id": "dim3",
            "name": "Test Dimension 1",  # Duplicate name for testing
            "type": "string",
            "title": "Test Dimension Duplicate",
            "description": "Duplicate dimension"
        }
    ]

    return mock_cja


@pytest.fixture
def sample_metrics_df():
    """Create a sample metrics DataFrame for testing"""
    return pd.DataFrame([
        {
            "id": "metric1",
            "name": "Test Metric 1",
            "type": "calculated",
            "title": "Test Metric 1 Title",
            "description": "Test metric description"
        },
        {
            "id": "metric2",
            "name": "Test Metric 2",
            "type": "standard",
            "title": "Test Metric 2 Title",
            "description": None
        }
    ])


@pytest.fixture
def sample_dimensions_df():
    """Create a sample dimensions DataFrame for testing"""
    return pd.DataFrame([
        {
            "id": "dim1",
            "name": "Test Dimension 1",
            "type": "string",
            "title": "Test Dimension 1 Title",
            "description": "Test dimension description"
        },
        {
            "id": "dim2",
            "name": "Test Dimension 2",
            "type": "string",
            "title": "Test Dimension 2 Title",
            "description": ""
        },
        {
            "id": "dim3",
            "name": "Test Dimension 1",  # Duplicate
            "type": "string",
            "title": "Test Dimension Duplicate",
            "description": "Duplicate dimension"
        }
    ])


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
    return pd.DataFrame({
        'id': [f'id_{i}' for i in range(size)],
        'name': [f'Name {i}' if i % 10 != 0 else f'Name {i % 50}' for i in range(size)],  # Some duplicates
        'type': ['metric' if i % 2 == 0 else 'calculated' for i in range(size)],
        'description': [f'Description {i}' if i % 3 != 0 else None for i in range(size)],  # Some nulls
        'title': [f'Title {i}' for i in range(size)]
    })


@pytest.fixture
def sample_data_dict(sample_metrics_df, sample_dimensions_df):
    """Create a sample data dictionary for output format testing"""
    return {
        'Metadata': pd.DataFrame({
            'Property': ['Generated At', 'Data View ID', 'Tool Version'],
            'Value': ['2024-01-01 12:00:00', 'dv_test_12345', '3.0']
        }),
        'Data Quality': pd.DataFrame([
            {
                'Severity': 'HIGH',
                'Category': 'Duplicates',
                'Type': 'Dimensions',
                'Item Name': 'Test Dimension 1',
                'Issue': 'Duplicate name found 2 times',
                'Details': 'This dimension appears multiple times'
            }
        ]),
        'DataView Details': pd.DataFrame({
            'Property': ['Name', 'ID', 'Owner'],
            'Value': ['Test Data View 1', 'dv_test_12345', 'Test Owner']
        }),
        'Metrics': sample_metrics_df,
        'Dimensions': sample_dimensions_df
    }


@pytest.fixture
def sample_metadata_dict():
    """Create a sample metadata dictionary for output format testing"""
    return {
        'Generated At': '2024-01-01 12:00:00',
        'Data View ID': 'dv_test_12345',
        'Data View Name': 'Test Data View 1',
        'Tool Version': '3.0',
        'Metrics Count': '2',
        'Dimensions Count': '3'
    }


@pytest.fixture
def large_metrics_df():
    """Generate large metrics DataFrame for performance testing"""
    data = []
    for i in range(1000):
        data.append({
            "id": f"metric_{i}",
            "name": f"Test Metric {i}",
            "type": "calculated",
            "title": f"Metric {i}",
            "description": f"Description {i}" if i % 2 == 0 else ""  # Some missing
        })
    return pd.DataFrame(data)


@pytest.fixture
def large_dimensions_df():
    """Generate large dimensions DataFrame for performance testing"""
    data = []
    for i in range(1000):
        data.append({
            "id": f"dimension_{i}",
            "name": f"Test Dimension {i}",
            "type": "string",
            "title": f"Dimension {i}",
            "description": f"Description {i}" if i % 3 == 0 else ""  # Some missing
        })
    return pd.DataFrame(data)
