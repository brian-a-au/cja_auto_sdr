"""Tests for Data View Comparison (Diff) functionality

Validates that:
1. DataViewSnapshot correctly captures data view state
2. SnapshotManager can save/load snapshots
3. DataViewComparator correctly identifies changes
4. Diff output writers produce correct output
5. CLI integration handles diff arguments correctly
"""
import pytest
import json
import os
import tempfile
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_sdr_generator import (
    ChangeType,
    ComponentDiff,
    MetadataDiff,
    DiffSummary,
    DiffResult,
    DataViewSnapshot,
    SnapshotManager,
    DataViewComparator,
    write_diff_console_output,
    write_diff_json_output,
    write_diff_markdown_output,
    write_diff_html_output,
    write_diff_excel_output,
    write_diff_csv_output,
    _format_side_by_side,
    _format_markdown_side_by_side,
)
import logging


# ==================== Fixtures ====================

@pytest.fixture
def sample_metrics():
    """Sample metrics for testing"""
    return [
        {"id": "metrics/pageviews", "name": "Page Views", "type": "int", "description": "Total page views"},
        {"id": "metrics/visits", "name": "Visits", "type": "int", "description": "Total visits"},
        {"id": "metrics/bounce_rate", "name": "Bounce Rate", "type": "decimal", "description": "Bounce percentage"},
    ]


@pytest.fixture
def sample_dimensions():
    """Sample dimensions for testing"""
    return [
        {"id": "dimensions/page", "name": "Page", "type": "string", "description": "Page URL"},
        {"id": "dimensions/device", "name": "Device Type", "type": "string", "description": "Device category"},
    ]


@pytest.fixture
def source_snapshot(sample_metrics, sample_dimensions):
    """Create a source snapshot for comparison"""
    return DataViewSnapshot(
        data_view_id="dv_source_12345",
        data_view_name="Source Data View",
        owner="admin@example.com",
        description="Source description",
        metrics=sample_metrics,
        dimensions=sample_dimensions
    )


@pytest.fixture
def target_snapshot_identical(sample_metrics, sample_dimensions):
    """Create an identical target snapshot"""
    return DataViewSnapshot(
        data_view_id="dv_target_67890",
        data_view_name="Target Data View",
        owner="admin@example.com",
        description="Target description",
        metrics=sample_metrics.copy(),
        dimensions=sample_dimensions.copy()
    )


@pytest.fixture
def target_snapshot_with_changes(sample_metrics, sample_dimensions):
    """Create a target snapshot with changes"""
    # Modify metrics
    modified_metrics = [
        {"id": "metrics/pageviews", "name": "Page Views", "type": "int", "description": "Updated description"},  # Modified
        # metrics/visits removed
        {"id": "metrics/bounce_rate", "name": "Bounce Rate", "type": "decimal", "description": "Bounce percentage"},
        {"id": "metrics/new_metric", "name": "New Metric", "type": "int", "description": "Added metric"},  # Added
    ]

    # Modify dimensions
    modified_dimensions = [
        {"id": "dimensions/page", "name": "Page URL", "type": "string", "description": "Page URL"},  # Name changed
        {"id": "dimensions/device", "name": "Device Type", "type": "string", "description": "Device category"},
        {"id": "dimensions/new_dim", "name": "New Dimension", "type": "string", "description": "Added"},  # Added
    ]

    return DataViewSnapshot(
        data_view_id="dv_target_67890",
        data_view_name="Target Data View",
        owner="admin@example.com",
        description="Target description",
        metrics=modified_metrics,
        dimensions=modified_dimensions
    )


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory"""
    return str(tmp_path)


@pytest.fixture
def logger():
    """Create a logger for testing"""
    return logging.getLogger("test_diff")


# ==================== DataViewSnapshot Tests ====================

class TestDataViewSnapshot:
    """Tests for DataViewSnapshot class"""

    def test_snapshot_creation(self, sample_metrics, sample_dimensions):
        """Test creating a snapshot"""
        snapshot = DataViewSnapshot(
            data_view_id="dv_test_12345",
            data_view_name="Test View",
            owner="test@example.com",
            description="Test description",
            metrics=sample_metrics,
            dimensions=sample_dimensions
        )

        assert snapshot.data_view_id == "dv_test_12345"
        assert snapshot.data_view_name == "Test View"
        assert len(snapshot.metrics) == 3
        assert len(snapshot.dimensions) == 2
        assert snapshot.snapshot_version == "1.0"
        assert snapshot.created_at is not None

    def test_snapshot_to_dict(self, source_snapshot):
        """Test converting snapshot to dictionary"""
        data = source_snapshot.to_dict()

        assert data['snapshot_version'] == "1.0"
        assert data['data_view_id'] == "dv_source_12345"
        assert data['data_view_name'] == "Source Data View"
        assert len(data['metrics']) == 3
        assert len(data['dimensions']) == 2
        assert 'created_at' in data

    def test_snapshot_from_dict(self, source_snapshot):
        """Test creating snapshot from dictionary"""
        data = source_snapshot.to_dict()
        restored = DataViewSnapshot.from_dict(data)

        assert restored.data_view_id == source_snapshot.data_view_id
        assert restored.data_view_name == source_snapshot.data_view_name
        assert len(restored.metrics) == len(source_snapshot.metrics)
        assert len(restored.dimensions) == len(source_snapshot.dimensions)

    def test_snapshot_defaults(self):
        """Test snapshot with minimal data"""
        snapshot = DataViewSnapshot(
            data_view_id="dv_test",
            data_view_name="Test"
        )

        assert snapshot.metrics == []
        assert snapshot.dimensions == []
        assert snapshot.owner == ""
        assert snapshot.description == ""


# ==================== SnapshotManager Tests ====================

class TestSnapshotManager:
    """Tests for SnapshotManager class"""

    def test_save_and_load_snapshot(self, source_snapshot, tmp_path, logger):
        """Test saving and loading a snapshot"""
        manager = SnapshotManager(logger)
        filepath = str(tmp_path / "test_snapshot.json")

        # Save
        saved_path = manager.save_snapshot(source_snapshot, filepath)
        assert os.path.exists(saved_path)

        # Load
        loaded = manager.load_snapshot(saved_path)
        assert loaded.data_view_id == source_snapshot.data_view_id
        assert loaded.data_view_name == source_snapshot.data_view_name
        assert len(loaded.metrics) == len(source_snapshot.metrics)

    def test_load_nonexistent_snapshot(self, tmp_path, logger):
        """Test loading a non-existent snapshot raises error"""
        manager = SnapshotManager(logger)

        with pytest.raises(FileNotFoundError):
            manager.load_snapshot(str(tmp_path / "nonexistent.json"))

    def test_load_invalid_snapshot(self, tmp_path, logger):
        """Test loading an invalid snapshot raises error"""
        manager = SnapshotManager(logger)
        filepath = str(tmp_path / "invalid.json")

        # Create invalid JSON (not a snapshot)
        with open(filepath, 'w') as f:
            json.dump({"foo": "bar"}, f)

        with pytest.raises(ValueError):
            manager.load_snapshot(filepath)

    def test_list_snapshots(self, source_snapshot, tmp_path, logger):
        """Test listing snapshots in a directory"""
        manager = SnapshotManager(logger)

        # Save multiple snapshots
        manager.save_snapshot(source_snapshot, str(tmp_path / "snap1.json"))
        manager.save_snapshot(source_snapshot, str(tmp_path / "snap2.json"))

        # Create a non-snapshot file
        with open(tmp_path / "other.json", 'w') as f:
            json.dump({"foo": "bar"}, f)

        snapshots = manager.list_snapshots(str(tmp_path))
        assert len(snapshots) == 2

    def test_list_snapshots_empty_directory(self, tmp_path, logger):
        """Test listing snapshots in an empty directory"""
        manager = SnapshotManager(logger)
        snapshots = manager.list_snapshots(str(tmp_path))
        assert snapshots == []


# ==================== DataViewComparator Tests ====================

class TestDataViewComparator:
    """Tests for DataViewComparator class"""

    def test_compare_identical_snapshots(self, source_snapshot, target_snapshot_identical, logger):
        """Test comparing identical snapshots"""
        comparator = DataViewComparator(logger)
        result = comparator.compare(source_snapshot, target_snapshot_identical)

        assert result.summary.has_changes is False
        assert result.summary.metrics_added == 0
        assert result.summary.metrics_removed == 0
        assert result.summary.metrics_modified == 0
        assert result.summary.dimensions_added == 0
        assert result.summary.dimensions_removed == 0
        assert result.summary.dimensions_modified == 0

    def test_compare_with_changes(self, source_snapshot, target_snapshot_with_changes, logger):
        """Test comparing snapshots with changes"""
        comparator = DataViewComparator(logger)
        result = comparator.compare(source_snapshot, target_snapshot_with_changes)

        assert result.summary.has_changes is True
        assert result.summary.metrics_added == 1  # new_metric
        assert result.summary.metrics_removed == 1  # visits
        assert result.summary.metrics_modified == 1  # pageviews (description changed)
        assert result.summary.dimensions_added == 1  # new_dim
        assert result.summary.dimensions_removed == 0
        assert result.summary.dimensions_modified == 1  # page (name changed)

    def test_compare_with_ignore_fields(self, source_snapshot, target_snapshot_with_changes, logger):
        """Test comparing with ignored fields"""
        comparator = DataViewComparator(logger, ignore_fields=['description', 'name'])
        result = comparator.compare(source_snapshot, target_snapshot_with_changes)

        # With name and description ignored, only adds/removes should be detected
        assert result.summary.metrics_modified == 0  # description change ignored
        assert result.summary.dimensions_modified == 0  # name change ignored

    def test_compare_custom_labels(self, source_snapshot, target_snapshot_identical, logger):
        """Test comparing with custom labels"""
        comparator = DataViewComparator(logger)
        result = comparator.compare(
            source_snapshot, target_snapshot_identical,
            source_label="Production", target_label="Staging"
        )

        assert result.source_label == "Production"
        assert result.target_label == "Staging"

    def test_change_types_correct(self, source_snapshot, target_snapshot_with_changes, logger):
        """Test that change types are correctly identified"""
        comparator = DataViewComparator(logger)
        result = comparator.compare(source_snapshot, target_snapshot_with_changes)

        # Check metric diffs
        metric_diffs = {d.id: d for d in result.metric_diffs}

        assert metric_diffs["metrics/new_metric"].change_type == ChangeType.ADDED
        assert metric_diffs["metrics/visits"].change_type == ChangeType.REMOVED
        assert metric_diffs["metrics/pageviews"].change_type == ChangeType.MODIFIED

    def test_changed_fields_tracked(self, source_snapshot, target_snapshot_with_changes, logger):
        """Test that changed fields are tracked for modified components"""
        comparator = DataViewComparator(logger)
        result = comparator.compare(source_snapshot, target_snapshot_with_changes)

        # Find the modified pageviews metric
        pageviews_diff = next(d for d in result.metric_diffs if d.id == "metrics/pageviews")

        assert pageviews_diff.change_type == ChangeType.MODIFIED
        assert 'description' in pageviews_diff.changed_fields


# ==================== DiffSummary Tests ====================

class TestDiffSummary:
    """Tests for DiffSummary class"""

    def test_has_changes_false(self):
        """Test has_changes returns False when no changes"""
        summary = DiffSummary()
        assert summary.has_changes is False

    def test_has_changes_true(self):
        """Test has_changes returns True when changes exist"""
        summary = DiffSummary(metrics_added=1)
        assert summary.has_changes is True

        summary2 = DiffSummary(dimensions_modified=2)
        assert summary2.has_changes is True

    def test_total_changes(self):
        """Test total_changes calculation"""
        summary = DiffSummary(
            metrics_added=1,
            metrics_removed=2,
            metrics_modified=3,
            dimensions_added=4,
            dimensions_removed=5,
            dimensions_modified=6
        )
        assert summary.total_changes == 21


# ==================== Diff Output Writer Tests ====================

class TestDiffOutputWriters:
    """Tests for diff output writers"""

    @pytest.fixture
    def sample_diff_result(self, source_snapshot, target_snapshot_with_changes, logger):
        """Create a sample diff result for output testing"""
        comparator = DataViewComparator(logger)
        return comparator.compare(
            source_snapshot, target_snapshot_with_changes,
            source_label="Source", target_label="Target"
        )

    def test_console_output(self, sample_diff_result):
        """Test console output generation"""
        output = write_diff_console_output(sample_diff_result)

        assert "DATA VIEW COMPARISON REPORT" in output
        assert "Source" in output
        assert "Target" in output
        assert "SUMMARY" in output
        assert "METRICS CHANGES" in output
        assert "DIMENSIONS CHANGES" in output

    def test_console_output_changes_only(self, sample_diff_result):
        """Test console output with changes_only flag"""
        output = write_diff_console_output(sample_diff_result, changes_only=True, use_color=False)

        assert "DATA VIEW COMPARISON REPORT" in output
        # Should still show changes
        assert "[+]" in output or "[-]" in output or "[~]" in output

    def test_console_output_summary_only(self, sample_diff_result):
        """Test console output with summary_only flag"""
        output = write_diff_console_output(sample_diff_result, summary_only=True)

        assert "SUMMARY" in output
        assert "METRICS CHANGES" not in output

    def test_json_output(self, sample_diff_result, temp_output_dir, logger):
        """Test JSON output generation"""
        filepath = write_diff_json_output(
            sample_diff_result, "test_diff", temp_output_dir, logger
        )

        assert os.path.exists(filepath)
        with open(filepath, 'r') as f:
            data = json.load(f)

        assert 'metadata' in data
        assert 'source' in data
        assert 'target' in data
        assert 'summary' in data
        assert 'metric_diffs' in data
        assert 'dimension_diffs' in data

    def test_markdown_output(self, sample_diff_result, temp_output_dir, logger):
        """Test Markdown output generation"""
        filepath = write_diff_markdown_output(
            sample_diff_result, "test_diff", temp_output_dir, logger
        )

        assert os.path.exists(filepath)
        with open(filepath, 'r') as f:
            content = f.read()

        assert "# Data View Comparison Report" in content
        assert "## Summary" in content
        assert "| Component |" in content

    def test_html_output(self, sample_diff_result, temp_output_dir, logger):
        """Test HTML output generation"""
        filepath = write_diff_html_output(
            sample_diff_result, "test_diff", temp_output_dir, logger
        )

        assert os.path.exists(filepath)
        with open(filepath, 'r') as f:
            content = f.read()

        assert "<!DOCTYPE html>" in content
        assert "Data View Comparison Report" in content
        assert "<table" in content

    def test_excel_output(self, sample_diff_result, temp_output_dir, logger):
        """Test Excel output generation"""
        filepath = write_diff_excel_output(
            sample_diff_result, "test_diff", temp_output_dir, logger
        )

        assert os.path.exists(filepath)
        assert filepath.endswith('.xlsx')

    def test_csv_output(self, sample_diff_result, temp_output_dir, logger):
        """Test CSV output generation"""
        dirpath = write_diff_csv_output(
            sample_diff_result, "test_diff", temp_output_dir, logger
        )

        assert os.path.isdir(dirpath)
        assert os.path.exists(os.path.join(dirpath, 'summary.csv'))
        assert os.path.exists(os.path.join(dirpath, 'metadata.csv'))
        assert os.path.exists(os.path.join(dirpath, 'metrics_diff.csv'))
        assert os.path.exists(os.path.join(dirpath, 'dimensions_diff.csv'))


# ==================== Edge Case Tests ====================

class TestEdgeCases:
    """Tests for edge cases"""

    def test_empty_snapshots(self, logger):
        """Test comparing empty snapshots"""
        source = DataViewSnapshot(
            data_view_id="dv_empty1",
            data_view_name="Empty 1",
            metrics=[],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_empty2",
            data_view_name="Empty 2",
            metrics=[],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        assert result.summary.has_changes is False
        assert result.summary.total_changes == 0

    def test_all_added(self, logger, sample_metrics, sample_dimensions):
        """Test when all items are added (empty source)"""
        source = DataViewSnapshot(
            data_view_id="dv_empty",
            data_view_name="Empty",
            metrics=[],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_full",
            data_view_name="Full",
            metrics=sample_metrics,
            dimensions=sample_dimensions
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        assert result.summary.metrics_added == 3
        assert result.summary.dimensions_added == 2
        assert result.summary.metrics_removed == 0

    def test_all_removed(self, logger, sample_metrics, sample_dimensions):
        """Test when all items are removed (empty target)"""
        source = DataViewSnapshot(
            data_view_id="dv_full",
            data_view_name="Full",
            metrics=sample_metrics,
            dimensions=sample_dimensions
        )
        target = DataViewSnapshot(
            data_view_id="dv_empty",
            data_view_name="Empty",
            metrics=[],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        assert result.summary.metrics_removed == 3
        assert result.summary.dimensions_removed == 2
        assert result.summary.metrics_added == 0

    def test_special_characters_in_names(self, logger):
        """Test handling of special characters in component names"""
        source = DataViewSnapshot(
            data_view_id="dv_special",
            data_view_name="Special <> & \"quotes\" View",
            metrics=[{"id": "m1", "name": "Metric with | pipe", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_special2",
            data_view_name="Special <> & \"quotes\" View 2",
            metrics=[{"id": "m1", "name": "Metric with | pipe", "type": "int"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # Should not raise any errors
        console_output = write_diff_console_output(result)
        assert "Special" in console_output


# ==================== Comparison Fields Tests ====================

class TestComparisonFields:
    """Tests for field comparison logic as documented in DIFF_COMPARISON.md"""

    def test_default_compare_fields(self, logger):
        """Test that default fields (name, title, description, type, schemaPath) are compared"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{
                "id": "m1",
                "name": "Original Name",
                "title": "Original Title",
                "description": "Original Description",
                "type": "int",
                "schemaPath": "/path/original"
            }],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[{
                "id": "m1",
                "name": "Changed Name",
                "title": "Changed Title",
                "description": "Changed Description",
                "type": "decimal",
                "schemaPath": "/path/changed"
            }],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        metric_diff = result.metric_diffs[0]
        assert metric_diff.change_type == ChangeType.MODIFIED
        # All 5 default fields should be detected as changed
        assert 'name' in metric_diff.changed_fields
        assert 'title' in metric_diff.changed_fields
        assert 'description' in metric_diff.changed_fields
        assert 'type' in metric_diff.changed_fields
        assert 'schemaPath' in metric_diff.changed_fields

    def test_id_based_matching(self, logger):
        """Test that components are matched by ID, not by name"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[
                {"id": "metrics/pageviews", "name": "Page Views", "type": "int"},
                {"id": "metrics/visits", "name": "Visits", "type": "int"}
            ],
            dimensions=[]
        )
        # Same IDs but names swapped - should be detected as MODIFIED, not ADD/REMOVE
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[
                {"id": "metrics/pageviews", "name": "Visits", "type": "int"},  # Name changed
                {"id": "metrics/visits", "name": "Page Views", "type": "int"}  # Name changed
            ],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # Should be 2 modified, 0 added, 0 removed (matched by ID)
        assert result.summary.metrics_modified == 2
        assert result.summary.metrics_added == 0
        assert result.summary.metrics_removed == 0

    def test_metadata_comparison(self, logger):
        """Test that data view metadata changes are tracked"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Original Name",
            owner="original@example.com",
            description="Original description",
            metrics=[],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Changed Name",
            owner="changed@example.com",
            description="Changed description",
            metrics=[],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # Metadata changes should be tracked
        assert result.metadata_diff.source_name == "Original Name"
        assert result.metadata_diff.target_name == "Changed Name"
        assert 'name' in result.metadata_diff.changed_fields
        assert 'owner' in result.metadata_diff.changed_fields
        assert 'description' in result.metadata_diff.changed_fields

    def test_unchanged_detection(self, logger):
        """Test that unchanged components are correctly identified"""
        metrics = [
            {"id": "m1", "name": "Metric 1", "type": "int", "description": "Desc 1"},
            {"id": "m2", "name": "Metric 2", "type": "int", "description": "Desc 2"},
        ]
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=metrics,
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=metrics.copy(),  # Identical
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        assert result.summary.metrics_unchanged == 2
        assert result.summary.metrics_modified == 0
        for diff in result.metric_diffs:
            assert diff.change_type == ChangeType.UNCHANGED

    def test_custom_ignore_fields(self, logger):
        """Test that --ignore-fields functionality works correctly"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{"id": "m1", "name": "Name", "description": "Old desc", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[{"id": "m1", "name": "Name", "description": "New desc", "type": "int"}],
            dimensions=[]
        )

        # Without ignore - should detect change
        comparator1 = DataViewComparator(logger)
        result1 = comparator1.compare(source, target)
        assert result1.summary.metrics_modified == 1

        # With ignore description - should not detect change
        comparator2 = DataViewComparator(logger, ignore_fields=['description'])
        result2 = comparator2.compare(source, target)
        assert result2.summary.metrics_modified == 0
        assert result2.summary.metrics_unchanged == 1


# ==================== CLI Argument Tests ====================

class TestCLIArguments:
    """Tests for CLI argument parsing related to diff feature"""

    def test_parse_ignore_fields(self):
        """Test that --ignore-fields argument is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        # Mock sys.argv
        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2',
                       '--ignore-fields', 'description,title']
            args = parse_arguments()
            assert args.ignore_fields == 'description,title'
            assert args.diff is True
        finally:
            sys.argv = original_argv

    def test_parse_diff_labels(self):
        """Test that --diff-labels argument is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2',
                       '--diff-labels', 'Production', 'Staging']
            args = parse_arguments()
            assert args.diff_labels == ['Production', 'Staging']
        finally:
            sys.argv = original_argv

    def test_parse_changes_only(self):
        """Test that --changes-only flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--changes-only']
            args = parse_arguments()
            assert args.changes_only is True
        finally:
            sys.argv = original_argv

    def test_parse_summary_flag(self):
        """Test that --summary flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--summary']
            args = parse_arguments()
            assert args.summary is True
        finally:
            sys.argv = original_argv

    def test_parse_snapshot_argument(self):
        """Test that --snapshot argument is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', 'dv_12345',
                       '--snapshot', './snapshots/baseline.json']
            args = parse_arguments()
            assert args.snapshot == './snapshots/baseline.json'
        finally:
            sys.argv = original_argv

    def test_parse_diff_snapshot_argument(self):
        """Test that --diff-snapshot argument is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', 'dv_12345',
                       '--diff-snapshot', './snapshots/baseline.json']
            args = parse_arguments()
            assert args.diff_snapshot == './snapshots/baseline.json'
        finally:
            sys.argv = original_argv


# ==================== Output Format Verification Tests ====================

class TestOutputFormatVerification:
    """Tests to verify output formats match documentation"""

    @pytest.fixture
    def diff_result_with_all_change_types(self, logger):
        """Create a diff result with all change types for output testing"""
        source = DataViewSnapshot(
            data_view_id="dv_source",
            data_view_name="Source View",
            owner="owner@test.com",
            description="Source description",
            metrics=[
                {"id": "m1", "name": "Unchanged Metric", "type": "int", "description": "Stays same"},
                {"id": "m2", "name": "Modified Metric", "type": "int", "description": "Old desc"},
                {"id": "m3", "name": "Removed Metric", "type": "int", "description": "Will be removed"},
            ],
            dimensions=[
                {"id": "d1", "name": "Unchanged Dim", "type": "string"},
            ]
        )
        target = DataViewSnapshot(
            data_view_id="dv_target",
            data_view_name="Target View",
            owner="owner@test.com",
            description="Target description",
            metrics=[
                {"id": "m1", "name": "Unchanged Metric", "type": "int", "description": "Stays same"},
                {"id": "m2", "name": "Modified Metric", "type": "int", "description": "New desc"},
                {"id": "m4", "name": "Added Metric", "type": "int", "description": "New metric"},
            ],
            dimensions=[
                {"id": "d1", "name": "Unchanged Dim", "type": "string"},
                {"id": "d2", "name": "Added Dim", "type": "string"},
            ]
        )

        comparator = DataViewComparator(logger)
        return comparator.compare(source, target, "Source", "Target")

    def test_console_output_contains_symbols(self, diff_result_with_all_change_types):
        """Test console output contains correct change symbols"""
        output = write_diff_console_output(diff_result_with_all_change_types, use_color=False)

        assert "[+]" in output  # Added
        assert "[-]" in output  # Removed
        assert "[~]" in output  # Modified

    def test_json_output_structure(self, diff_result_with_all_change_types, tmp_path, logger):
        """Test JSON output has correct structure"""
        filepath = write_diff_json_output(
            diff_result_with_all_change_types, "test", str(tmp_path), logger
        )

        with open(filepath) as f:
            data = json.load(f)

        # Verify structure matches documentation
        assert 'metadata' in data
        assert 'source' in data
        assert 'target' in data
        assert 'summary' in data
        assert 'metric_diffs' in data
        assert 'dimension_diffs' in data

        # Verify change types
        change_types = [d['change_type'] for d in data['metric_diffs']]
        assert 'added' in change_types
        assert 'removed' in change_types
        assert 'modified' in change_types
        assert 'unchanged' in change_types

    def test_summary_statistics_accuracy(self, diff_result_with_all_change_types):
        """Test that summary statistics are accurate"""
        summary = diff_result_with_all_change_types.summary

        # Metrics: 1 unchanged, 1 modified, 1 removed, 1 added
        assert summary.metrics_unchanged == 1
        assert summary.metrics_modified == 1
        assert summary.metrics_removed == 1
        assert summary.metrics_added == 1

        # Dimensions: 1 unchanged, 1 added
        assert summary.dimensions_unchanged == 1
        assert summary.dimensions_added == 1
        assert summary.dimensions_removed == 0
        assert summary.dimensions_modified == 0

        # Total
        assert summary.total_changes == 4  # 1 mod + 1 rem + 1 add (metrics) + 1 add (dim)
        assert summary.has_changes is True


# ==================== New Feature Tests (v3.0.10) ====================

class TestExtendedFieldComparison:
    """Tests for extended field comparison (attribution, format, etc.)"""

    def test_extended_compare_fields_list(self, logger):
        """Test that EXTENDED_COMPARE_FIELDS contains expected fields"""
        assert 'name' in DataViewComparator.EXTENDED_COMPARE_FIELDS
        assert 'attribution' in DataViewComparator.EXTENDED_COMPARE_FIELDS
        assert 'format' in DataViewComparator.EXTENDED_COMPARE_FIELDS
        assert 'precision' in DataViewComparator.EXTENDED_COMPARE_FIELDS
        assert 'hidden' in DataViewComparator.EXTENDED_COMPARE_FIELDS
        assert 'bucketing' in DataViewComparator.EXTENDED_COMPARE_FIELDS
        assert 'persistence' in DataViewComparator.EXTENDED_COMPARE_FIELDS
        assert 'formula' in DataViewComparator.EXTENDED_COMPARE_FIELDS

    def test_use_extended_fields_flag(self, logger):
        """Test that use_extended_fields enables extended comparison"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{
                "id": "m1", "name": "Metric",
                "type": "int", "hidden": False, "precision": 2
            }],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[{
                "id": "m1", "name": "Metric",
                "type": "int", "hidden": True, "precision": 4  # Changed
            }],
            dimensions=[]
        )

        # Without extended - only basic fields compared
        comparator1 = DataViewComparator(logger, use_extended_fields=False)
        result1 = comparator1.compare(source, target)
        # 'hidden' and 'precision' are not in default fields
        assert result1.summary.metrics_modified == 0

        # With extended - should detect hidden and precision changes
        comparator2 = DataViewComparator(logger, use_extended_fields=True)
        result2 = comparator2.compare(source, target)
        assert result2.summary.metrics_modified == 1
        assert 'hidden' in result2.metric_diffs[0].changed_fields
        assert 'precision' in result2.metric_diffs[0].changed_fields

    def test_attribution_settings_comparison(self, logger):
        """Test comparison of attribution settings (nested structure)"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{
                "id": "m1", "name": "Metric",
                "attribution": {"model": "lastTouch", "lookback": 30}
            }],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[{
                "id": "m1", "name": "Metric",
                "attribution": {"model": "firstTouch", "lookback": 30}  # Model changed
            }],
            dimensions=[]
        )

        comparator = DataViewComparator(logger, use_extended_fields=True)
        result = comparator.compare(source, target)

        assert result.summary.metrics_modified == 1
        assert 'attribution' in result.metric_diffs[0].changed_fields


class TestShowOnlyFilter:
    """Tests for --show-only filter functionality"""

    def test_show_only_added(self, logger, sample_metrics, sample_dimensions):
        """Test filtering to show only added items"""
        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "Existing", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[
                {"id": "m1", "name": "Existing", "type": "int"},
                {"id": "m2", "name": "New", "type": "int"}  # Added
            ],
            dimensions=[]
        )

        comparator = DataViewComparator(logger, show_only=['added'])
        result = comparator.compare(source, target)

        # Should only contain added items
        assert len(result.metric_diffs) == 1
        assert result.metric_diffs[0].change_type == ChangeType.ADDED

    def test_show_only_removed(self, logger):
        """Test filtering to show only removed items"""
        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[
                {"id": "m1", "name": "Keep", "type": "int"},
                {"id": "m2", "name": "Remove", "type": "int"}
            ],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[{"id": "m1", "name": "Keep", "type": "int"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger, show_only=['removed'])
        result = comparator.compare(source, target)

        assert len(result.metric_diffs) == 1
        assert result.metric_diffs[0].change_type == ChangeType.REMOVED

    def test_show_only_multiple_types(self, logger):
        """Test filtering with multiple change types"""
        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[
                {"id": "m1", "name": "Unchanged", "type": "int"},
                {"id": "m2", "name": "Modified", "type": "int", "description": "Old"},
                {"id": "m3", "name": "Removed", "type": "int"}
            ],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[
                {"id": "m1", "name": "Unchanged", "type": "int"},
                {"id": "m2", "name": "Modified", "type": "int", "description": "New"},
                {"id": "m4", "name": "Added", "type": "int"}
            ],
            dimensions=[]
        )

        comparator = DataViewComparator(logger, show_only=['added', 'modified'])
        result = comparator.compare(source, target)

        # Should contain added and modified, but not unchanged or removed
        change_types = [d.change_type for d in result.metric_diffs]
        assert ChangeType.ADDED in change_types
        assert ChangeType.MODIFIED in change_types
        assert ChangeType.UNCHANGED not in change_types
        assert ChangeType.REMOVED not in change_types


class TestMetricsOnlyAndDimensionsOnly:
    """Tests for --metrics-only and --dimensions-only flags"""

    def test_metrics_only_flag(self, logger, sample_metrics, sample_dimensions):
        """Test that --metrics-only excludes dimensions"""
        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=sample_metrics,
            dimensions=sample_dimensions
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=sample_metrics,
            dimensions=[]  # All dimensions removed
        )

        comparator = DataViewComparator(logger, metrics_only=True)
        result = comparator.compare(source, target)

        # Dimensions should be empty (not compared)
        assert len(result.dimension_diffs) == 0
        # Metrics should be compared
        assert len(result.metric_diffs) > 0

    def test_dimensions_only_flag(self, logger, sample_metrics, sample_dimensions):
        """Test that --dimensions-only excludes metrics"""
        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=sample_metrics,
            dimensions=sample_dimensions
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[],  # All metrics removed
            dimensions=sample_dimensions
        )

        comparator = DataViewComparator(logger, dimensions_only=True)
        result = comparator.compare(source, target)

        # Metrics should be empty (not compared)
        assert len(result.metric_diffs) == 0
        # Dimensions should be compared
        assert len(result.dimension_diffs) > 0


class TestSideBySideOutput:
    """Tests for side-by-side output view"""

    def test_side_by_side_console_output(self, logger):
        """Test that side-by-side console output contains table characters"""
        from cja_sdr_generator import _format_side_by_side

        diff = ComponentDiff(
            id="m1",
            name="Test Metric",
            change_type=ChangeType.MODIFIED,
            source_data={"name": "Old Name", "description": "Old desc"},
            target_data={"name": "New Name", "description": "New desc"},
            changed_fields={
                "name": ("Old Name", "New Name"),
                "description": ("Old desc", "New desc")
            }
        )

        lines = _format_side_by_side(diff, "Source", "Target")

        # Should contain table border characters
        assert any("┌" in line for line in lines)
        assert any("│" in line for line in lines)
        assert any("└" in line for line in lines)

    def test_side_by_side_markdown_output(self, logger):
        """Test that side-by-side markdown output creates a table"""
        from cja_sdr_generator import _format_markdown_side_by_side

        diff = ComponentDiff(
            id="m1",
            name="Test Metric",
            change_type=ChangeType.MODIFIED,
            source_data={"name": "Old", "type": "int"},
            target_data={"name": "New", "type": "decimal"},
            changed_fields={
                "name": ("Old", "New"),
                "type": ("int", "decimal")
            }
        )

        lines = _format_markdown_side_by_side(diff, "Source", "Target")

        # Should contain markdown table
        assert any("| Field |" in line for line in lines)
        assert any("| --- |" in line for line in lines)
        assert any("`name`" in line for line in lines)

    def test_console_output_with_side_by_side_flag(self, logger):
        """Test console output when side_by_side=True"""
        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "Old Name", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[{"id": "m1", "name": "New Name", "type": "int"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        output = write_diff_console_output(result, side_by_side=True)

        # Should contain table border characters for modified items
        assert "┌" in output or "[~]" in output


# ==================== Large Dataset Performance Tests ====================

class TestLargeDatasetPerformance:
    """Tests for large dataset handling (500+ components)"""

    @pytest.fixture
    def large_metrics(self):
        """Generate 500+ metrics for performance testing"""
        return [
            {
                "id": f"metrics/metric_{i}",
                "name": f"Metric {i}",
                "type": "int" if i % 2 == 0 else "decimal",
                "description": f"Description for metric {i}",
                "schemaPath": f"/schema/path/{i}"
            }
            for i in range(600)
        ]

    @pytest.fixture
    def large_dimensions(self):
        """Generate 200+ dimensions for performance testing"""
        return [
            {
                "id": f"dimensions/dim_{i}",
                "name": f"Dimension {i}",
                "type": "string",
                "description": f"Description for dimension {i}",
                "schemaPath": f"/schema/path/dim/{i}"
            }
            for i in range(250)
        ]

    def test_compare_large_identical_datasets(self, logger, large_metrics, large_dimensions):
        """Test comparison of large identical datasets completes quickly"""
        import time

        source = DataViewSnapshot(
            data_view_id="dv_large_1",
            data_view_name="Large Source",
            metrics=large_metrics,
            dimensions=large_dimensions
        )
        target = DataViewSnapshot(
            data_view_id="dv_large_2",
            data_view_name="Large Target",
            metrics=large_metrics.copy(),
            dimensions=large_dimensions.copy()
        )

        start = time.time()
        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        elapsed = time.time() - start

        # Should complete in reasonable time (< 5 seconds for 850 components)
        assert elapsed < 5.0
        assert result.summary.metrics_unchanged == 600
        assert result.summary.dimensions_unchanged == 250
        assert result.summary.has_changes is False

    def test_compare_large_datasets_with_changes(self, logger, large_metrics, large_dimensions):
        """Test comparison of large datasets with mixed changes"""
        import time

        # Modify some items in target
        target_metrics = large_metrics.copy()
        for i in range(50):  # Modify 50 metrics
            target_metrics[i] = {**target_metrics[i], "description": f"Modified desc {i}"}
        # Add 50 new metrics
        for i in range(600, 650):
            target_metrics.append({
                "id": f"metrics/new_metric_{i}",
                "name": f"New Metric {i}",
                "type": "int",
                "description": f"New description {i}"
            })

        source = DataViewSnapshot(
            data_view_id="dv_large_1",
            data_view_name="Large Source",
            metrics=large_metrics,
            dimensions=large_dimensions
        )
        target = DataViewSnapshot(
            data_view_id="dv_large_2",
            data_view_name="Large Target",
            metrics=target_metrics,
            dimensions=large_dimensions.copy()
        )

        start = time.time()
        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        elapsed = time.time() - start

        # Should complete in reasonable time
        assert elapsed < 5.0
        assert result.summary.metrics_modified == 50
        assert result.summary.metrics_added == 50
        assert result.summary.has_changes is True

    def test_large_dataset_memory_efficiency(self, logger, large_metrics, large_dimensions):
        """Test that large dataset comparison doesn't consume excessive memory"""
        import sys

        source = DataViewSnapshot(
            data_view_id="dv_large_1",
            data_view_name="Large Source",
            metrics=large_metrics,
            dimensions=large_dimensions
        )
        target = DataViewSnapshot(
            data_view_id="dv_large_2",
            data_view_name="Large Target",
            metrics=large_metrics.copy(),
            dimensions=large_dimensions.copy()
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # Result should be created without errors
        assert result is not None
        # Summary should have correct counts
        assert result.summary.source_metrics_count == 600
        assert result.summary.source_dimensions_count == 250


# ==================== Unicode Edge Case Tests ====================

class TestUnicodeEdgeCases:
    """Tests for Unicode handling in diff comparison"""

    def test_emoji_in_names(self, logger):
        """Test components with emoji in names"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test 📊",
            metrics=[{"id": "m1", "name": "Pageviews 📈", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test 📊",
            metrics=[{"id": "m1", "name": "Pageviews 📉", "type": "int"}],  # Different emoji
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        assert result.summary.metrics_modified == 1
        assert "📈" in str(result.metric_diffs[0].changed_fields.get('name', ('', ''))[0])

    def test_rtl_text_in_descriptions(self, logger):
        """Test components with RTL (Hebrew/Arabic) text"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{"id": "m1", "name": "Metric", "description": "תיאור עברי", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[{"id": "m1", "name": "Metric", "description": "תיאור אחר", "type": "int"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        assert result.summary.metrics_modified == 1

    def test_special_characters_in_fields(self, logger):
        """Test components with special characters"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test <>&\"'",
            metrics=[{
                "id": "m1",
                "name": "Metric with <html> & \"quotes\"",
                "description": "Line1\nLine2\tTabbed",
                "type": "int"
            }],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test <>&\"'",
            metrics=[{
                "id": "m1",
                "name": "Metric with <html> & \"quotes\"",
                "description": "Different\nContent",
                "type": "int"
            }],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        assert result.summary.metrics_modified == 1

    def test_unicode_in_json_output(self, logger, tmp_path):
        """Test that Unicode is preserved in JSON output"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="数据视图",  # Chinese
            metrics=[{"id": "m1", "name": "指标 🎯", "type": "int", "description": "描述文字"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="数据视图",
            metrics=[{"id": "m1", "name": "指标 🎯", "type": "int", "description": "新描述"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        filepath = write_diff_json_output(result, "unicode_test", str(tmp_path), logger)

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Unicode should be preserved, not escaped
        assert "数据视图" in content
        assert "指标" in content


# ==================== Deeply Nested Structure Tests ====================

class TestDeeplyNestedStructures:
    """Tests for deeply nested configuration structures"""

    def test_nested_attribution_config(self, logger):
        """Test comparison of nested attribution configuration"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{
                "id": "m1",
                "name": "Revenue",
                "attribution": {
                    "model": "lastTouch",
                    "lookback": {
                        "type": "visitor",
                        "granularity": "day",
                        "numPeriods": 30
                    }
                }
            }],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[{
                "id": "m1",
                "name": "Revenue",
                "attribution": {
                    "model": "lastTouch",
                    "lookback": {
                        "type": "visitor",
                        "granularity": "day",
                        "numPeriods": 60  # Changed from 30 to 60
                    }
                }
            }],
            dimensions=[]
        )

        comparator = DataViewComparator(logger, use_extended_fields=True)
        result = comparator.compare(source, target)

        assert result.summary.metrics_modified == 1
        assert 'attribution' in result.metric_diffs[0].changed_fields

    def test_nested_format_config(self, logger):
        """Test comparison of nested format configuration"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{
                "id": "m1",
                "name": "Currency",
                "format": {
                    "type": "currency",
                    "currency": "USD",
                    "precision": 2,
                    "negativeFormat": "parentheses"
                }
            }],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[{
                "id": "m1",
                "name": "Currency",
                "format": {
                    "type": "currency",
                    "currency": "EUR",  # Changed
                    "precision": 2,
                    "negativeFormat": "parentheses"
                }
            }],
            dimensions=[]
        )

        comparator = DataViewComparator(logger, use_extended_fields=True)
        result = comparator.compare(source, target)

        assert result.summary.metrics_modified == 1

    def test_nested_bucketing_config(self, logger):
        """Test comparison of nested bucketing configuration for dimensions"""
        source = DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[],
            dimensions=[{
                "id": "d1",
                "name": "Price Range",
                "bucketing": {
                    "enabled": True,
                    "buckets": [0, 100, 500, 1000],
                    "labels": ["Low", "Medium", "High", "Premium"]
                }
            }]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2",
            data_view_name="Test",
            metrics=[],
            dimensions=[{
                "id": "d1",
                "name": "Price Range",
                "bucketing": {
                    "enabled": True,
                    "buckets": [0, 50, 200, 500, 1000],  # Changed
                    "labels": ["Very Low", "Low", "Medium", "High", "Premium"]  # Changed
                }
            }]
        )

        comparator = DataViewComparator(logger, use_extended_fields=True)
        result = comparator.compare(source, target)

        assert result.summary.dimensions_modified == 1


# ==================== Concurrent Comparison Thread Safety Tests ====================

class TestConcurrentComparison:
    """Tests for thread safety in concurrent comparisons"""

    def test_concurrent_comparisons(self, logger, sample_metrics, sample_dimensions):
        """Test multiple concurrent comparisons don't interfere"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        source = DataViewSnapshot(
            data_view_id="dv_source",
            data_view_name="Source",
            metrics=sample_metrics,
            dimensions=sample_dimensions
        )

        targets = [
            DataViewSnapshot(
                data_view_id=f"dv_target_{i}",
                data_view_name=f"Target {i}",
                metrics=[{**m, "description": f"Modified {i}"} for m in sample_metrics],
                dimensions=sample_dimensions
            )
            for i in range(10)
        ]

        results = []
        errors = []

        def run_comparison(target):
            try:
                comparator = DataViewComparator(logger)
                return comparator.compare(source, target)
            except Exception as e:
                return e

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_comparison, t) for t in targets]
            for future in as_completed(futures):
                result = future.result()
                if isinstance(result, Exception):
                    errors.append(result)
                else:
                    results.append(result)

        # All comparisons should complete without errors
        assert len(errors) == 0
        assert len(results) == 10

        # Each result should be valid
        for result in results:
            assert result.summary is not None
            assert result.summary.metrics_modified == 3  # All metrics modified


# ==================== Snapshot Version Migration Tests ====================

class TestSnapshotVersionMigration:
    """Tests for handling different snapshot versions"""

    def test_load_v1_snapshot(self, logger, tmp_path):
        """Test loading a v1.0 snapshot format"""
        v1_snapshot = {
            "snapshot_version": "1.0",
            "created_at": "2025-01-01T00:00:00",
            "data_view_id": "dv_legacy",
            "data_view_name": "Legacy View",
            "owner": "legacy@test.com",
            "description": "Old format",
            "metrics": [{"id": "m1", "name": "Metric", "type": "int"}],
            "dimensions": [],
            "metadata": {"tool_version": "3.0.0"}
        }

        filepath = str(tmp_path / "v1_snapshot.json")
        with open(filepath, 'w') as f:
            json.dump(v1_snapshot, f)

        manager = SnapshotManager(logger)
        loaded = manager.load_snapshot(filepath)

        assert loaded.snapshot_version == "1.0"
        assert loaded.data_view_id == "dv_legacy"
        assert len(loaded.metrics) == 1

    def test_snapshot_without_metadata(self, logger, tmp_path):
        """Test loading snapshot with minimal/missing metadata"""
        minimal_snapshot = {
            "snapshot_version": "1.0",
            "data_view_id": "dv_minimal",
            "data_view_name": "Minimal",
            "metrics": [],
            "dimensions": []
            # No metadata, owner, description, created_at
        }

        filepath = str(tmp_path / "minimal_snapshot.json")
        with open(filepath, 'w') as f:
            json.dump(minimal_snapshot, f)

        manager = SnapshotManager(logger)
        loaded = manager.load_snapshot(filepath)

        assert loaded.data_view_id == "dv_minimal"
        assert loaded.owner == ""
        assert loaded.description == ""

    def test_compare_different_version_snapshots(self, logger, tmp_path):
        """Test comparing snapshots from different versions"""
        old_snapshot = DataViewSnapshot(
            snapshot_version="1.0",
            data_view_id="dv_old",
            data_view_name="Old",
            metrics=[{"id": "m1", "name": "Metric", "type": "int"}],
            dimensions=[]
        )
        old_snapshot.metadata = {"tool_version": "2.0.0"}

        new_snapshot = DataViewSnapshot(
            snapshot_version="1.0",
            data_view_id="dv_new",
            data_view_name="New",
            metrics=[{"id": "m1", "name": "Metric", "type": "int"}],
            dimensions=[]
        )
        new_snapshot.metadata = {"tool_version": "3.0.10"}

        comparator = DataViewComparator(logger)
        result = comparator.compare(old_snapshot, new_snapshot)

        # Should work regardless of tool version differences
        assert result is not None
        assert result.summary.metrics_unchanged == 1


# ==================== New CLI Argument Tests ====================

class TestNewCLIArguments:
    """Tests for new CLI arguments added in v3.0.10"""

    def test_parse_show_only_argument(self):
        """Test that --show-only argument is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2',
                       '--show-only', 'added,modified']
            args = parse_arguments()
            assert args.show_only == 'added,modified'
        finally:
            sys.argv = original_argv

    def test_parse_metrics_only_flag(self):
        """Test that --metrics-only flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--metrics-only']
            args = parse_arguments()
            assert args.metrics_only is True
        finally:
            sys.argv = original_argv

    def test_parse_dimensions_only_flag(self):
        """Test that --dimensions-only flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--dimensions-only']
            args = parse_arguments()
            assert args.dimensions_only is True
        finally:
            sys.argv = original_argv

    def test_parse_extended_fields_flag(self):
        """Test that --extended-fields flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--extended-fields']
            args = parse_arguments()
            assert args.extended_fields is True
        finally:
            sys.argv = original_argv

    def test_parse_side_by_side_flag(self):
        """Test that --side-by-side flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--side-by-side']
            args = parse_arguments()
            assert args.side_by_side is True
        finally:
            sys.argv = original_argv


# ==================== v3.0.10 New Feature Tests ====================

class TestDiffSummaryPercentages:
    """Tests for new DiffSummary percentage properties"""

    def test_metrics_change_percent(self, logger):
        """Test metrics_change_percent calculation"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            source_metrics_count=100,
            target_metrics_count=100,
            metrics_added=5,
            metrics_removed=3,
            metrics_modified=2
        )

        assert summary.metrics_changed == 10
        assert summary.metrics_change_percent == 10.0

    def test_dimensions_change_percent(self, logger):
        """Test dimensions_change_percent calculation"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            source_dimensions_count=50,
            target_dimensions_count=60,
            dimensions_added=10,
            dimensions_removed=0,
            dimensions_modified=5
        )

        assert summary.dimensions_changed == 15
        # Should use max(50, 60) = 60 as base
        assert summary.dimensions_change_percent == 25.0

    def test_zero_components_percent(self, logger):
        """Test percentage is 0 when no components exist"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            source_metrics_count=0,
            target_metrics_count=0
        )

        assert summary.metrics_change_percent == 0.0

    def test_natural_language_summary(self, logger):
        """Test natural_language_summary property"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            metrics_added=3,
            metrics_removed=2,
            metrics_modified=1,
            dimensions_added=1,
            dimensions_removed=0,
            dimensions_modified=2
        )

        nl_summary = summary.natural_language_summary
        assert "Metrics:" in nl_summary
        assert "3 added" in nl_summary
        assert "2 removed" in nl_summary
        assert "Dimensions:" in nl_summary

    def test_natural_language_summary_no_changes(self, logger):
        """Test natural_language_summary when no changes"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary()
        assert summary.natural_language_summary == "No changes detected"

    def test_total_added(self, logger):
        """Test total_added property sums across all component types"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            metrics_added=5,
            dimensions_added=3
        )
        assert summary.total_added == 8

    def test_total_removed(self, logger):
        """Test total_removed property sums across all component types"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            metrics_removed=2,
            dimensions_removed=4
        )
        assert summary.total_removed == 6

    def test_total_modified(self, logger):
        """Test total_modified property sums across all component types"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            metrics_modified=3,
            dimensions_modified=7
        )
        assert summary.total_modified == 10

    def test_total_summary_with_changes(self, logger):
        """Test total_summary property returns formatted string"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            metrics_added=3,
            metrics_removed=2,
            metrics_modified=1,
            dimensions_added=1,
            dimensions_removed=4,
            dimensions_modified=2
        )
        total_summary = summary.total_summary
        assert "4 added" in total_summary  # 3 + 1
        assert "6 removed" in total_summary  # 2 + 4
        assert "3 modified" in total_summary  # 1 + 2

    def test_total_summary_no_changes(self, logger):
        """Test total_summary returns 'No changes' when empty"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary()
        assert summary.total_summary == "No changes"

    def test_total_summary_partial_changes(self, logger):
        """Test total_summary only shows non-zero values"""
        from cja_sdr_generator import DiffSummary

        summary = DiffSummary(
            metrics_added=5,
            dimensions_added=2
        )
        total_summary = summary.total_summary
        assert "7 added" in total_summary
        assert "removed" not in total_summary
        assert "modified" not in total_summary


class TestColoredConsoleOutput:
    """Tests for ANSI color-coded console output"""

    def test_console_output_with_color(self, logger):
        """Test console output includes ANSI color codes when enabled"""
        from cja_sdr_generator import write_diff_console_output, DataViewSnapshot, DataViewComparator

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "Test", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[{"id": "m2", "name": "New", "type": "int"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        output = write_diff_console_output(result, use_color=True)

        # Should contain ANSI escape codes
        assert "\x1b[" in output

    def test_console_output_without_color(self, logger):
        """Test console output has no ANSI codes when disabled"""
        from cja_sdr_generator import write_diff_console_output, DataViewSnapshot, DataViewComparator

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "Test", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[{"id": "m2", "name": "New", "type": "int"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        output = write_diff_console_output(result, use_color=False)

        # Should NOT contain ANSI escape codes
        assert "\x1b[" not in output
        # But should still have change symbols
        assert "[+]" in output or "[-]" in output


class TestGroupByFieldOutput:
    """Tests for --group-by-field output mode"""

    def test_grouped_by_field_output(self, logger):
        """Test group by field output format"""
        from cja_sdr_generator import (
            write_diff_grouped_by_field_output, DataViewSnapshot,
            DataViewComparator
        )

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[
                {"id": "m1", "name": "A", "description": "Old A", "type": "int"},
                {"id": "m2", "name": "B", "description": "Old B", "type": "int"},
            ],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[
                {"id": "m1", "name": "A", "description": "New A", "type": "int"},
                {"id": "m2", "name": "B", "description": "New B", "type": "int"},
            ],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        output = write_diff_grouped_by_field_output(result, use_color=False)

        assert "GROUPED BY FIELD" in output
        assert "CHANGES BY FIELD" in output
        assert "description" in output.lower()

    def test_grouped_by_field_limit_default(self, logger):
        """Test that default limit of 10 truncates output"""
        from cja_sdr_generator import (
            write_diff_grouped_by_field_output, DataViewSnapshot,
            DataViewComparator
        )

        # Create 15 metrics with description changes to exceed the default limit of 10
        source_metrics = [
            {"id": f"m{i}", "name": f"Metric {i}", "description": f"Old desc {i}", "type": "int"}
            for i in range(15)
        ]
        target_metrics = [
            {"id": f"m{i}", "name": f"Metric {i}", "description": f"New desc {i}", "type": "int"}
            for i in range(15)
        ]

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=source_metrics, dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=target_metrics, dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # Default limit=10 should show truncation message
        output = write_diff_grouped_by_field_output(result, use_color=False, limit=10)
        assert "... and 5 more" in output

    def test_grouped_by_field_limit_zero_shows_all(self, logger):
        """Test that limit=0 shows all items without truncation"""
        from cja_sdr_generator import (
            write_diff_grouped_by_field_output, DataViewSnapshot,
            DataViewComparator
        )

        # Create 15 metrics with description changes
        source_metrics = [
            {"id": f"m{i}", "name": f"Metric {i}", "description": f"Old desc {i}", "type": "int"}
            for i in range(15)
        ]
        target_metrics = [
            {"id": f"m{i}", "name": f"Metric {i}", "description": f"New desc {i}", "type": "int"}
            for i in range(15)
        ]

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=source_metrics, dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=target_metrics, dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # limit=0 should show all items without truncation
        output = write_diff_grouped_by_field_output(result, use_color=False, limit=0)
        assert "... and" not in output
        # All 15 metrics should be shown
        for i in range(15):
            assert f"m{i}" in output

    def test_grouped_by_field_limit_custom(self, logger):
        """Test that custom limit value works correctly"""
        from cja_sdr_generator import (
            write_diff_grouped_by_field_output, DataViewSnapshot,
            DataViewComparator
        )

        # Create 20 metrics with description changes
        source_metrics = [
            {"id": f"m{i}", "name": f"Metric {i}", "description": f"Old desc {i}", "type": "int"}
            for i in range(20)
        ]
        target_metrics = [
            {"id": f"m{i}", "name": f"Metric {i}", "description": f"New desc {i}", "type": "int"}
            for i in range(20)
        ]

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=source_metrics, dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=target_metrics, dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # limit=5 should show "... and 15 more"
        output = write_diff_grouped_by_field_output(result, use_color=False, limit=5)
        assert "... and 15 more" in output

    def test_grouped_by_field_limit_added_removed(self, logger):
        """Test that limit applies to ADDED and REMOVED sections too"""
        from cja_sdr_generator import (
            write_diff_grouped_by_field_output, DataViewSnapshot,
            DataViewComparator
        )

        # Source has 15 metrics, target has none (all removed)
        source_metrics = [
            {"id": f"m{i}", "name": f"Metric {i}", "description": f"Desc {i}", "type": "int"}
            for i in range(15)
        ]

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=source_metrics, dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[], dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)

        # Default limit=10 should truncate removed list
        output_limited = write_diff_grouped_by_field_output(result, use_color=False, limit=10)
        assert "REMOVED (15)" in output_limited
        assert "... and 5 more" in output_limited

        # limit=0 should show all
        output_unlimited = write_diff_grouped_by_field_output(result, use_color=False, limit=0)
        assert "REMOVED (15)" in output_unlimited
        assert "... and" not in output_unlimited


class TestPRCommentOutput:
    """Tests for --format-pr-comment output"""

    def test_pr_comment_output_format(self, logger):
        """Test PR comment markdown format"""
        from cja_sdr_generator import (
            write_diff_pr_comment_output, DataViewSnapshot,
            DataViewComparator
        )

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "A", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[
                {"id": "m1", "name": "A", "type": "decimal"},  # Type change - breaking
                {"id": "m2", "name": "B", "type": "int"}
            ],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        output = write_diff_pr_comment_output(result)

        # Should be markdown format
        assert "### 📊 Data View Comparison" in output
        assert "| Component |" in output
        assert "<details>" in output
        assert "</details>" in output

    def test_pr_comment_breaking_changes(self, logger):
        """Test PR comment shows breaking changes"""
        from cja_sdr_generator import (
            write_diff_pr_comment_output, DataViewSnapshot,
            DataViewComparator
        )

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "A", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[{"id": "m1", "name": "A", "type": "decimal"}],  # Type change
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        output = write_diff_pr_comment_output(result)

        # Should flag breaking change
        assert "Breaking Changes" in output


class TestBreakingChangeDetection:
    """Tests for breaking change detection"""

    def test_detect_type_change_as_breaking(self, logger):
        """Test type changes are flagged as breaking"""
        from cja_sdr_generator import detect_breaking_changes, DataViewSnapshot, DataViewComparator

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "A", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[{"id": "m1", "name": "A", "type": "decimal"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        breaking = detect_breaking_changes(result)

        assert len(breaking) == 1
        assert breaking[0]['change_type'] == 'type_changed'
        assert breaking[0]['severity'] == 'high'

    def test_detect_removal_as_breaking(self, logger):
        """Test component removal is flagged as breaking"""
        from cja_sdr_generator import detect_breaking_changes, DataViewSnapshot, DataViewComparator

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "A", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        breaking = detect_breaking_changes(result)

        assert len(breaking) == 1
        assert breaking[0]['change_type'] == 'removed'

    def test_no_breaking_changes(self, logger):
        """Test no breaking changes when only non-breaking changes"""
        from cja_sdr_generator import detect_breaking_changes, DataViewSnapshot, DataViewComparator

        source = DataViewSnapshot(
            data_view_id="dv_1", data_view_name="Source",
            metrics=[{"id": "m1", "name": "A", "description": "Old", "type": "int"}],
            dimensions=[]
        )
        target = DataViewSnapshot(
            data_view_id="dv_2", data_view_name="Target",
            metrics=[{"id": "m1", "name": "A", "description": "New", "type": "int"}],
            dimensions=[]
        )

        comparator = DataViewComparator(logger)
        result = comparator.compare(source, target)
        breaking = detect_breaking_changes(result)

        # Description change is not breaking
        assert len(breaking) == 0


class TestNewCLIFlags:
    """Tests for new v3.0.10 CLI flags"""

    def test_parse_no_color_flag(self):
        """Test that --no-color flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--no-color']
            args = parse_arguments()
            assert args.no_color is True
        finally:
            sys.argv = original_argv

    def test_parse_quiet_diff_flag(self):
        """Test that --quiet-diff flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--quiet-diff']
            args = parse_arguments()
            assert args.quiet_diff is True
        finally:
            sys.argv = original_argv

    def test_parse_reverse_diff_flag(self):
        """Test that --reverse-diff flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--reverse-diff']
            args = parse_arguments()
            assert args.reverse_diff is True
        finally:
            sys.argv = original_argv

    def test_parse_warn_threshold_flag(self):
        """Test that --warn-threshold flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--warn-threshold', '10.5']
            args = parse_arguments()
            assert args.warn_threshold == 10.5
        finally:
            sys.argv = original_argv

    def test_parse_group_by_field_flag(self):
        """Test that --group-by-field flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--group-by-field']
            args = parse_arguments()
            assert args.group_by_field is True
        finally:
            sys.argv = original_argv

    def test_parse_group_by_field_limit_flag(self):
        """Test that --group-by-field-limit flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            # Test custom value
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--group-by-field', '--group-by-field-limit', '25']
            args = parse_arguments()
            assert args.group_by_field_limit == 25

            # Test zero (unlimited)
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--group-by-field', '--group-by-field-limit', '0']
            args = parse_arguments()
            assert args.group_by_field_limit == 0
        finally:
            sys.argv = original_argv

    def test_parse_group_by_field_limit_default(self):
        """Test that --group-by-field-limit defaults to 10"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--group-by-field']
            args = parse_arguments()
            assert args.group_by_field_limit == 10
        finally:
            sys.argv = original_argv

    def test_parse_diff_output_flag(self):
        """Test that --diff-output flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--diff-output', '/tmp/diff.txt']
            args = parse_arguments()
            assert args.diff_output == '/tmp/diff.txt'
        finally:
            sys.argv = original_argv

    def test_parse_format_pr_comment_flag(self):
        """Test that --format-pr-comment flag is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--diff', 'dv_1', 'dv_2', '--format-pr-comment']
            args = parse_arguments()
            assert args.format_pr_comment is True
        finally:
            sys.argv = original_argv


# ==================== Ambiguous Name Resolution Tests ====================

class TestAmbiguousNameResolution:
    """Tests for ambiguous data view name handling in diff commands.

    When a data view name maps to multiple data views, the diff functionality
    must reject the ambiguous name and require the user to specify an exact ID.
    """

    def test_resolve_single_name_to_single_id(self):
        """Test that a unique name resolves to exactly one ID"""
        from cja_sdr_generator import resolve_data_view_names
        from unittest.mock import patch, MagicMock

        mock_data_views = [
            {"id": "dv_12345", "name": "Unique Analytics"},
            {"id": "dv_67890", "name": "Other View"},
        ]

        with patch('cja_sdr_generator.cjapy') as mock_cjapy:
            mock_cjapy.CJA.return_value = MagicMock()
            mock_cjapy.importConfigFile = MagicMock()
            with patch('cja_sdr_generator.get_cached_data_views', return_value=mock_data_views):
                logger = logging.getLogger('test')
                resolved_ids, name_map = resolve_data_view_names(
                    ["Unique Analytics"], "config.json", logger
                )

                assert len(resolved_ids) == 1
                assert resolved_ids[0] == "dv_12345"

    def test_resolve_name_to_multiple_ids(self):
        """Test that an ambiguous name returns ALL matching IDs"""
        from cja_sdr_generator import resolve_data_view_names
        from unittest.mock import patch, MagicMock

        mock_data_views = [
            {"id": "dv_prod_001", "name": "Analytics"},
            {"id": "dv_staging_001", "name": "Analytics"},
            {"id": "dv_dev_001", "name": "Analytics"},
            {"id": "dv_other_999", "name": "Other View"},
        ]

        with patch('cja_sdr_generator.cjapy') as mock_cjapy:
            mock_cjapy.CJA.return_value = MagicMock()
            mock_cjapy.importConfigFile = MagicMock()
            # Mock the cached data views function
            with patch('cja_sdr_generator.get_cached_data_views', return_value=mock_data_views):
                logger = logging.getLogger('test')
                resolved_ids, name_map = resolve_data_view_names(
                    ["Analytics"], "config.json", logger
                )

                # Should return all 3 matching IDs
                assert len(resolved_ids) == 3
                assert "dv_prod_001" in resolved_ids
                assert "dv_staging_001" in resolved_ids
                assert "dv_dev_001" in resolved_ids
                assert "dv_other_999" not in resolved_ids

                # name_map should track the mapping
                assert "Analytics" in name_map
                assert len(name_map["Analytics"]) == 3

    def test_resolve_explicit_id_unchanged(self):
        """Test that explicit IDs pass through unchanged"""
        from cja_sdr_generator import resolve_data_view_names
        from unittest.mock import patch, MagicMock

        mock_data_views = [
            {"id": "dv_12345", "name": "Analytics"},
        ]

        with patch('cja_sdr_generator.cjapy') as mock_cjapy:
            mock_cjapy.CJA.return_value = MagicMock()
            mock_cjapy.importConfigFile = MagicMock()
            with patch('cja_sdr_generator.get_cached_data_views', return_value=mock_data_views):
                logger = logging.getLogger('test')
                resolved_ids, name_map = resolve_data_view_names(
                    ["dv_12345"], "config.json", logger
                )

                assert len(resolved_ids) == 1
                assert resolved_ids[0] == "dv_12345"
                # IDs don't create name_map entries
                assert len(name_map) == 0

    def test_diff_rejects_ambiguous_source_name(self):
        """Test that diff command rejects ambiguous source name"""
        # This tests the CLI validation logic that should reject
        # names that resolve to multiple data views
        from cja_sdr_generator import resolve_data_view_names
        from unittest.mock import patch, MagicMock

        mock_data_views = [
            {"id": "dv_prod_001", "name": "Analytics"},
            {"id": "dv_staging_001", "name": "Analytics"},  # Duplicate name
        ]

        with patch('cja_sdr_generator.cjapy') as mock_cjapy:
            mock_cjapy.CJA.return_value = MagicMock()
            mock_cjapy.importConfigFile = MagicMock()
            with patch('cja_sdr_generator.get_cached_data_views', return_value=mock_data_views):
                logger = logging.getLogger('test')
                # When diff receives "Analytics", it should get multiple IDs back
                resolved_ids, _ = resolve_data_view_names(
                    ["Analytics"], "config.json", logger
                )

                # Validation: more than 1 result means ambiguous
                assert len(resolved_ids) > 1, "Ambiguous name should return multiple IDs"

    def test_diff_command_handles_source_target_separately(self):
        """Test that diff command resolves source and target independently"""
        from cja_sdr_generator import resolve_data_view_names
        from unittest.mock import patch, MagicMock

        mock_data_views = [
            {"id": "dv_prod_001", "name": "Production Analytics"},
            {"id": "dv_staging_001", "name": "Staging Analytics"},
        ]

        with patch('cja_sdr_generator.cjapy') as mock_cjapy:
            mock_cjapy.CJA.return_value = MagicMock()
            mock_cjapy.importConfigFile = MagicMock()
            with patch('cja_sdr_generator.get_cached_data_views', return_value=mock_data_views):
                logger = logging.getLogger('test')

                # Resolve source separately
                source_ids, _ = resolve_data_view_names(
                    ["Production Analytics"], "config.json", logger
                )

                # Resolve target separately
                target_ids, _ = resolve_data_view_names(
                    ["Staging Analytics"], "config.json", logger
                )

                # Each should resolve to exactly one
                assert len(source_ids) == 1
                assert len(target_ids) == 1
                assert source_ids[0] == "dv_prod_001"
                assert target_ids[0] == "dv_staging_001"

    def test_mixed_id_and_name_resolution(self):
        """Test resolving mix of explicit IDs and names"""
        from cja_sdr_generator import resolve_data_view_names
        from unittest.mock import patch, MagicMock

        mock_data_views = [
            {"id": "dv_prod_001", "name": "Production Analytics"},
            {"id": "dv_staging_001", "name": "Staging Analytics"},
        ]

        with patch('cja_sdr_generator.cjapy') as mock_cjapy:
            mock_cjapy.CJA.return_value = MagicMock()
            mock_cjapy.importConfigFile = MagicMock()
            with patch('cja_sdr_generator.get_cached_data_views', return_value=mock_data_views):
                logger = logging.getLogger('test')

                # Source by ID, target by name
                source_ids, _ = resolve_data_view_names(
                    ["dv_prod_001"], "config.json", logger
                )
                target_ids, _ = resolve_data_view_names(
                    ["Staging Analytics"], "config.json", logger
                )

                assert len(source_ids) == 1
                assert len(target_ids) == 1
                assert source_ids[0] == "dv_prod_001"
                assert target_ids[0] == "dv_staging_001"


# ==================== Levenshtein Distance Tests ====================

class TestLevenshteinDistance:
    """Tests for fuzzy matching using Levenshtein distance."""

    def test_levenshtein_identical_strings(self):
        """Test that identical strings have distance 0"""
        from cja_sdr_generator import levenshtein_distance
        assert levenshtein_distance("hello", "hello") == 0
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("Analytics", "Analytics") == 0

    def test_levenshtein_empty_string(self):
        """Test distance with empty string"""
        from cja_sdr_generator import levenshtein_distance
        assert levenshtein_distance("", "hello") == 5
        assert levenshtein_distance("hello", "") == 5

    def test_levenshtein_single_edit(self):
        """Test single character edits"""
        from cja_sdr_generator import levenshtein_distance
        # Substitution
        assert levenshtein_distance("cat", "bat") == 1
        # Insertion
        assert levenshtein_distance("cat", "cats") == 1
        # Deletion
        assert levenshtein_distance("cats", "cat") == 1

    def test_levenshtein_multiple_edits(self):
        """Test multiple edits"""
        from cja_sdr_generator import levenshtein_distance
        assert levenshtein_distance("kitten", "sitting") == 3
        assert levenshtein_distance("saturday", "sunday") == 3


class TestFindSimilarNames:
    """Tests for finding similar data view names."""

    def test_find_exact_case_insensitive_match(self):
        """Test finding exact case-insensitive match"""
        from cja_sdr_generator import find_similar_names
        names = ["Production Analytics", "Staging View", "Dev Environment"]
        similar = find_similar_names("production analytics", names)

        assert len(similar) >= 1
        assert similar[0][0] == "Production Analytics"
        assert similar[0][1] == 0  # Distance 0 for case-insensitive match

    def test_find_similar_with_typo(self):
        """Test finding similar names with typos"""
        from cja_sdr_generator import find_similar_names
        names = ["Production Analytics", "Staging View", "Development"]
        similar = find_similar_names("Prodction Analytics", names)  # Missing 'u'

        assert len(similar) >= 1
        assert "Production Analytics" in [s[0] for s in similar]

    def test_find_similar_limits_results(self):
        """Test that results are limited to max_suggestions"""
        from cja_sdr_generator import find_similar_names
        names = [f"View {i}" for i in range(20)]
        similar = find_similar_names("View", names, max_suggestions=3)

        assert len(similar) <= 3

    def test_find_similar_respects_max_distance(self):
        """Test that max_distance is respected"""
        from cja_sdr_generator import find_similar_names
        names = ["Analytics", "Completely Different Name"]
        similar = find_similar_names("Analytics", names, max_distance=2)

        # "Completely Different Name" should be filtered out due to high distance
        assert all(s[1] <= 2 for s in similar)

    def test_find_similar_empty_list(self):
        """Test with empty available names"""
        from cja_sdr_generator import find_similar_names
        similar = find_similar_names("Analytics", [])
        assert len(similar) == 0


# ==================== DataViewCache Tests ====================

class TestDataViewCache:
    """Tests for the data view caching mechanism."""

    def test_cache_set_and_get(self):
        """Test setting and getting from cache"""
        from cja_sdr_generator import DataViewCache

        # Create a fresh cache instance for testing
        cache = DataViewCache.__new__(DataViewCache)
        cache._cache = {}
        cache._ttl_seconds = 300
        cache._initialized = True

        test_data = [{"id": "dv_1", "name": "Test"}]
        cache.set("test_config.json", test_data)
        result = cache.get("test_config.json")

        assert result == test_data

    def test_cache_miss(self):
        """Test cache miss returns None"""
        from cja_sdr_generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._cache = {}
        cache._ttl_seconds = 300
        cache._initialized = True

        result = cache.get("nonexistent.json")
        assert result is None

    def test_cache_clear(self):
        """Test clearing the cache"""
        from cja_sdr_generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._cache = {}
        cache._ttl_seconds = 300
        cache._initialized = True

        cache.set("config1.json", [{"id": "dv_1"}])
        cache.set("config2.json", [{"id": "dv_2"}])
        cache.clear()

        assert cache.get("config1.json") is None
        assert cache.get("config2.json") is None

    def test_cache_ttl_expiry(self):
        """Test that cache expires after TTL"""
        from cja_sdr_generator import DataViewCache
        import time

        cache = DataViewCache.__new__(DataViewCache)
        cache._cache = {}
        cache._ttl_seconds = 0.1  # Very short TTL for testing
        cache._initialized = True

        cache.set("config.json", [{"id": "dv_1"}])
        time.sleep(0.2)  # Wait for TTL to expire

        result = cache.get("config.json")
        assert result is None  # Should be expired


# ==================== Snapshot-to-Snapshot Comparison Tests ====================

class TestSnapshotToSnapshotComparison:
    """Tests for comparing two snapshot files directly."""

    @pytest.fixture
    def temp_snapshots(self, tmp_path, sample_metrics, sample_dimensions):
        """Create temporary snapshot files for testing"""
        import copy

        # Source snapshot - use deep copy to ensure isolation
        source_metrics = copy.deepcopy(sample_metrics)
        source_dimensions = copy.deepcopy(sample_dimensions)
        source_snapshot = {
            "snapshot_version": "1.0",
            "created_at": "2025-01-01T10:00:00.000000",
            "data_view_id": "dv_source",
            "data_view_name": "Source Analytics",
            "owner": "admin@example.com",
            "description": "Source data view",
            "metrics": source_metrics,
            "dimensions": source_dimensions,
            "metadata": {"tool_version": "3.0.10"}
        }

        # Target snapshot (with changes) - use deep copy and modify
        target_metrics = copy.deepcopy(sample_metrics)
        target_metrics[0]["description"] = "Modified description"
        target_dimensions = copy.deepcopy(sample_dimensions)
        target_snapshot = {
            "snapshot_version": "1.0",
            "created_at": "2025-01-15T10:00:00.000000",
            "data_view_id": "dv_target",
            "data_view_name": "Target Analytics",
            "owner": "admin@example.com",
            "description": "Target data view",
            "metrics": target_metrics,
            "dimensions": target_dimensions,
            "metadata": {"tool_version": "3.0.10"}
        }

        source_file = tmp_path / "source_snapshot.json"
        target_file = tmp_path / "target_snapshot.json"

        with open(source_file, 'w') as f:
            json.dump(source_snapshot, f)
        with open(target_file, 'w') as f:
            json.dump(target_snapshot, f)

        return str(source_file), str(target_file)

    def test_compare_snapshots_basic(self, temp_snapshots):
        """Test basic snapshot-to-snapshot comparison"""
        from cja_sdr_generator import handle_compare_snapshots_command

        source_file, target_file = temp_snapshots
        success, has_changes, exit_code = handle_compare_snapshots_command(
            source_file=source_file,
            target_file=target_file,
            quiet=True,
            quiet_diff=True
        )

        assert success is True
        assert has_changes is True  # We modified one metric

    def test_compare_snapshots_identical(self, tmp_path, sample_metrics, sample_dimensions):
        """Test comparing identical snapshots"""
        from cja_sdr_generator import handle_compare_snapshots_command

        snapshot_data = {
            "snapshot_version": "1.0",
            "created_at": "2025-01-01T10:00:00.000000",
            "data_view_id": "dv_test",
            "data_view_name": "Test Analytics",
            "owner": "admin@example.com",
            "description": "Test",
            "metrics": sample_metrics,
            "dimensions": sample_dimensions,
            "metadata": {}
        }

        file1 = tmp_path / "snap1.json"
        file2 = tmp_path / "snap2.json"

        with open(file1, 'w') as f:
            json.dump(snapshot_data, f)
        with open(file2, 'w') as f:
            json.dump(snapshot_data, f)

        success, has_changes, _ = handle_compare_snapshots_command(
            source_file=str(file1),
            target_file=str(file2),
            quiet=True,
            quiet_diff=True
        )

        assert success is True
        assert has_changes is False

    def test_compare_snapshots_file_not_found(self, tmp_path):
        """Test error handling for missing snapshot file"""
        from cja_sdr_generator import handle_compare_snapshots_command

        success, _, _ = handle_compare_snapshots_command(
            source_file=str(tmp_path / "nonexistent.json"),
            target_file=str(tmp_path / "also_nonexistent.json"),
            quiet=True,
            quiet_diff=True
        )

        assert success is False

    def test_compare_snapshots_with_reverse(self, temp_snapshots):
        """Test reverse comparison flag"""
        from cja_sdr_generator import handle_compare_snapshots_command

        source_file, target_file = temp_snapshots
        success, has_changes, _ = handle_compare_snapshots_command(
            source_file=source_file,
            target_file=target_file,
            reverse_diff=True,
            quiet=True,
            quiet_diff=True
        )

        assert success is True
        assert has_changes is True


# ==================== CLI Arguments for New Features ====================

class TestNewFeatureCLIArguments:
    """Tests for CLI argument parsing of new features."""

    def test_parse_compare_snapshots_argument(self):
        """Test that --compare-snapshots is parsed correctly"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator.py', '--compare-snapshots', 'source.json', 'target.json']
            args = parse_arguments()
            assert args.compare_snapshots == ['source.json', 'target.json']
        finally:
            sys.argv = original_argv

    def test_compare_snapshots_with_options(self):
        """Test --compare-snapshots with additional options"""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = [
                'cja_sdr_generator.py',
                '--compare-snapshots', 'a.json', 'b.json',
                '--changes-only',
                '--format', 'json'
            ]
            args = parse_arguments()
            assert args.compare_snapshots == ['a.json', 'b.json']
            assert args.changes_only is True
            assert args.format == 'json'
        finally:
            sys.argv = original_argv


# ==================== Interactive Prompt Tests ====================

class TestPromptForSelection:
    """Tests for interactive selection prompt."""

    def test_prompt_returns_none_for_non_tty(self):
        """Test that prompt returns None when not in interactive terminal"""
        from cja_sdr_generator import prompt_for_selection
        from unittest.mock import patch

        # Mock sys.stdin.isatty() to return False
        with patch('sys.stdin.isatty', return_value=False):
            options = [("dv_1", "Option 1"), ("dv_2", "Option 2")]
            result = prompt_for_selection(options, "Select one:")
            assert result is None

    def test_prompt_handles_valid_selection(self):
        """Test that valid selection returns correct ID"""
        from cja_sdr_generator import prompt_for_selection
        from unittest.mock import patch

        options = [("dv_1", "Option 1"), ("dv_2", "Option 2")]

        with patch('sys.stdin.isatty', return_value=True):
            with patch('builtins.input', return_value='1'):
                result = prompt_for_selection(options, "Select one:")
                assert result == "dv_1"

    def test_prompt_handles_cancel(self):
        """Test that cancel selection returns None"""
        from cja_sdr_generator import prompt_for_selection
        from unittest.mock import patch

        options = [("dv_1", "Option 1"), ("dv_2", "Option 2")]

        with patch('sys.stdin.isatty', return_value=True):
            with patch('builtins.input', return_value='0'):
                result = prompt_for_selection(options, "Select one:")
                assert result is None

    def test_prompt_handles_eof(self):
        """Test that EOF is handled gracefully"""
        from cja_sdr_generator import prompt_for_selection
        from unittest.mock import patch

        options = [("dv_1", "Option 1")]

        with patch('sys.stdin.isatty', return_value=True):
            with patch('builtins.input', side_effect=EOFError):
                result = prompt_for_selection(options, "Select:")
                assert result is None


# ==================== Auto-Snapshot Tests ====================

class TestAutoSnapshotFilenameGeneration:
    """Tests for snapshot filename generation"""

    def test_generate_filename_with_name(self):
        """Test filename generation with data view name"""
        manager = SnapshotManager()
        filename = manager.generate_snapshot_filename("dv_12345", "My Data View")

        assert filename.startswith("My_Data_View_dv_12345_")
        assert filename.endswith(".json")
        # Check timestamp format (YYYYMMDD_HHMMSS)
        parts = filename.replace(".json", "").split("_")
        assert len(parts[-2]) == 8  # YYYYMMDD
        assert len(parts[-1]) == 6  # HHMMSS

    def test_generate_filename_without_name(self):
        """Test filename generation without data view name"""
        manager = SnapshotManager()
        filename = manager.generate_snapshot_filename("dv_67890")

        assert filename.startswith("dv_67890_")
        assert filename.endswith(".json")

    def test_generate_filename_sanitizes_special_chars(self):
        """Test that special characters in name are sanitized"""
        manager = SnapshotManager()
        filename = manager.generate_snapshot_filename("dv_123", "My/Data:View*Name?")

        # Special chars should be replaced with underscores
        assert "/" not in filename
        assert ":" not in filename
        assert "*" not in filename
        assert "?" not in filename
        assert filename.startswith("My_Data_View_Name_")

    def test_generate_filename_truncates_long_names(self):
        """Test that long names are truncated"""
        manager = SnapshotManager()
        long_name = "A" * 100
        filename = manager.generate_snapshot_filename("dv_123", long_name)

        # Name should be truncated to 50 chars
        name_part = filename.split("_dv_123_")[0]
        assert len(name_part) <= 50


class TestRetentionPolicy:
    """Tests for snapshot retention policy"""

    def test_retention_keeps_all_when_zero(self):
        """Test that keep_last=0 keeps all snapshots"""
        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple snapshots
            for i in range(5):
                snapshot = DataViewSnapshot(
                    data_view_id="dv_test",
                    data_view_name="Test",
                    owner="test",
                    description="test",
                    metrics=[],
                    dimensions=[]
                )
                manager.save_snapshot(snapshot, os.path.join(tmpdir, f"snapshot_{i}.json"))

            deleted = manager.apply_retention_policy(tmpdir, "dv_test", keep_last=0)
            assert deleted == []
            assert len(os.listdir(tmpdir)) == 5

    def test_retention_deletes_old_snapshots(self):
        """Test that old snapshots are deleted beyond retention limit"""
        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create 5 snapshots with different timestamps
            from datetime import datetime, timedelta
            from unittest.mock import patch

            for i in range(5):
                timestamp = datetime.now() - timedelta(days=5-i)
                snapshot = DataViewSnapshot(
                    data_view_id="dv_test",
                    data_view_name="Test",
                    owner="test",
                    description="test",
                    metrics=[],
                    dimensions=[]
                )
                # Manually set created_at for ordering
                snapshot.created_at = timestamp.isoformat()
                manager.save_snapshot(snapshot, os.path.join(tmpdir, f"snapshot_{i}.json"))

            # Keep only last 2
            deleted = manager.apply_retention_policy(tmpdir, "dv_test", keep_last=2)

            assert len(deleted) == 3
            remaining = os.listdir(tmpdir)
            assert len(remaining) == 2

    def test_retention_only_affects_matching_data_view(self):
        """Test that retention only deletes snapshots for the specified data view"""
        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create snapshots for two different data views
            for dv_id in ["dv_a", "dv_b"]:
                for i in range(3):
                    snapshot = DataViewSnapshot(
                        data_view_id=dv_id,
                        data_view_name=f"Test {dv_id}",
                        owner="test",
                        description="test",
                        metrics=[],
                        dimensions=[]
                    )
                    manager.save_snapshot(snapshot, os.path.join(tmpdir, f"{dv_id}_snapshot_{i}.json"))

            # Apply retention only to dv_a
            deleted = manager.apply_retention_policy(tmpdir, "dv_a", keep_last=1)

            assert len(deleted) == 2
            # dv_b should still have all 3
            remaining = manager.list_snapshots(tmpdir)
            dv_b_count = sum(1 for s in remaining if s['data_view_id'] == 'dv_b')
            assert dv_b_count == 3

    def test_retention_handles_empty_directory(self):
        """Test retention with empty directory"""
        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            deleted = manager.apply_retention_policy(tmpdir, "dv_test", keep_last=5)
            assert deleted == []

    def test_retention_handles_nonexistent_directory(self):
        """Test retention with non-existent directory"""
        manager = SnapshotManager()
        deleted = manager.apply_retention_policy("/nonexistent/path", "dv_test", keep_last=5)
        assert deleted == []


class TestAutoSnapshotCLIArguments:
    """Tests for auto-snapshot CLI argument parsing"""

    def test_auto_snapshot_flag_default(self):
        """Test that --auto-snapshot defaults to False"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', 'dv_123']):
            args = parse_arguments()
            assert args.auto_snapshot is False

    def test_auto_snapshot_flag_enabled(self):
        """Test that --auto-snapshot can be enabled"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', '--diff', 'dv_a', 'dv_b', '--auto-snapshot']):
            args = parse_arguments()
            assert args.auto_snapshot is True

    def test_snapshot_dir_default(self):
        """Test that --snapshot-dir has correct default"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', 'dv_123']):
            args = parse_arguments()
            assert args.snapshot_dir == './snapshots'

    def test_snapshot_dir_custom(self):
        """Test that --snapshot-dir can be customized"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', '--diff', 'dv_a', 'dv_b', '--snapshot-dir', './my_snapshots']):
            args = parse_arguments()
            assert args.snapshot_dir == './my_snapshots'

    def test_keep_last_default(self):
        """Test that --keep-last defaults to 0 (keep all)"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', 'dv_123']):
            args = parse_arguments()
            assert args.keep_last == 0

    def test_keep_last_custom(self):
        """Test that --keep-last can be set"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', '--diff', 'dv_a', 'dv_b', '--keep-last', '10']):
            args = parse_arguments()
            assert args.keep_last == 10

    def test_all_auto_snapshot_flags_together(self):
        """Test all auto-snapshot flags used together"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', [
            'prog', '--diff', 'dv_a', 'dv_b',
            '--auto-snapshot',
            '--snapshot-dir', './history',
            '--keep-last', '5'
        ]):
            args = parse_arguments()
            assert args.auto_snapshot is True
            assert args.snapshot_dir == './history'
            assert args.keep_last == 5

    def test_compare_with_prev_flag_default(self):
        """Test that --compare-with-prev defaults to False"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', 'dv_123']):
            args = parse_arguments()
            assert args.compare_with_prev is False

    def test_compare_with_prev_flag_enabled(self):
        """Test that --compare-with-prev can be enabled"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', ['prog', 'dv_123', '--compare-with-prev']):
            args = parse_arguments()
            assert args.compare_with_prev is True

    def test_compare_with_prev_with_snapshot_dir(self):
        """Test --compare-with-prev works with --snapshot-dir"""
        from cja_sdr_generator import parse_arguments
        from unittest.mock import patch
        import sys

        with patch.object(sys, 'argv', [
            'prog', 'dv_123', '--compare-with-prev', '--snapshot-dir', './my_snapshots'
        ]):
            args = parse_arguments()
            assert args.compare_with_prev is True
            assert args.snapshot_dir == './my_snapshots'


class TestGetMostRecentSnapshot:
    """Tests for SnapshotManager.get_most_recent_snapshot method"""

    def test_get_most_recent_snapshot_returns_latest(self):
        """Test that get_most_recent_snapshot returns the most recent snapshot"""
        from cja_sdr_generator import SnapshotManager, DataViewSnapshot
        import time

        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create older snapshot
            old_snapshot = DataViewSnapshot(
                data_view_id="dv_test",
                data_view_name="Test View",
                created_at="2024-01-01T10:00:00",
                metrics=[],
                dimensions=[]
            )
            old_path = os.path.join(tmpdir, "old_snapshot.json")
            manager.save_snapshot(old_snapshot, old_path)

            # Create newer snapshot
            new_snapshot = DataViewSnapshot(
                data_view_id="dv_test",
                data_view_name="Test View",
                created_at="2024-06-01T10:00:00",
                metrics=[],
                dimensions=[]
            )
            new_path = os.path.join(tmpdir, "new_snapshot.json")
            manager.save_snapshot(new_snapshot, new_path)

            # Get most recent
            result = manager.get_most_recent_snapshot(tmpdir, "dv_test")
            assert result == new_path

    def test_get_most_recent_snapshot_filters_by_data_view(self):
        """Test that get_most_recent_snapshot only returns snapshots for specified data view"""
        from cja_sdr_generator import SnapshotManager, DataViewSnapshot

        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create snapshot for dv_other
            other_snapshot = DataViewSnapshot(
                data_view_id="dv_other",
                data_view_name="Other View",
                created_at="2024-06-01T10:00:00",
                metrics=[],
                dimensions=[]
            )
            other_path = os.path.join(tmpdir, "other_snapshot.json")
            manager.save_snapshot(other_snapshot, other_path)

            # Create snapshot for dv_test (older)
            test_snapshot = DataViewSnapshot(
                data_view_id="dv_test",
                data_view_name="Test View",
                created_at="2024-01-01T10:00:00",
                metrics=[],
                dimensions=[]
            )
            test_path = os.path.join(tmpdir, "test_snapshot.json")
            manager.save_snapshot(test_snapshot, test_path)

            # Should return dv_test snapshot, not dv_other (even though dv_other is newer)
            result = manager.get_most_recent_snapshot(tmpdir, "dv_test")
            assert result == test_path

    def test_get_most_recent_snapshot_returns_none_if_no_snapshots(self):
        """Test that get_most_recent_snapshot returns None when no snapshots exist"""
        from cja_sdr_generator import SnapshotManager

        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = manager.get_most_recent_snapshot(tmpdir, "dv_nonexistent")
            assert result is None

    def test_get_most_recent_snapshot_returns_none_for_empty_dir(self):
        """Test that get_most_recent_snapshot returns None for empty directory"""
        from cja_sdr_generator import SnapshotManager

        manager = SnapshotManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = manager.get_most_recent_snapshot(tmpdir, "dv_test")
            assert result is None

    def test_get_most_recent_snapshot_returns_none_for_nonexistent_dir(self):
        """Test that get_most_recent_snapshot returns None for non-existent directory"""
        from cja_sdr_generator import SnapshotManager

        manager = SnapshotManager()
        result = manager.get_most_recent_snapshot("/nonexistent/path", "dv_test")
        assert result is None
