"""Tests for lazy-forwarding infrastructure and all modules using make_getattr().

Covers:
- Direct unit tests for core/lazy.py make_getattr() helper
- Positive tests: lazy-forwarded attributes resolve correctly
- Negative tests: unknown attributes raise AttributeError
"""

import importlib

import pytest

from cja_auto_sdr.core.lazy import make_getattr

# ---------------------------------------------------------------------------
# Section 1: Direct unit tests for make_getattr()
# ---------------------------------------------------------------------------


class TestMakeGetattr:
    """Unit tests for the make_getattr() factory function itself."""

    def test_resolves_from_target_module(self):
        """make_getattr resolves an attribute from a single target module."""
        getter = make_getattr(
            "test_module",
            ["__version__"],
            target_module="cja_auto_sdr.core.version",
        )
        result = getter("__version__")
        assert isinstance(result, str)
        assert "." in result  # version string like "3.2.7"

    def test_raises_attribute_error_for_unknown_name(self):
        """make_getattr raises AttributeError for names not in export list."""
        getter = make_getattr(
            "test_module",
            ["__version__"],
            target_module="cja_auto_sdr.core.version",
        )
        with pytest.raises(AttributeError, match="test_module"):
            getter("nonexistent_attribute_xyz")

    def test_raises_value_error_without_target_or_mapping(self):
        """make_getattr raises ValueError when neither target_module nor mapping given."""
        with pytest.raises(ValueError, match="target_module or mapping is required"):
            make_getattr("test_module", ["some_name"])

    def test_works_with_explicit_mapping(self):
        """make_getattr resolves using explicit name-to-module mapping."""
        getter = make_getattr(
            "test_module",
            ["__version__", "CircuitState"],
            mapping={
                "__version__": "cja_auto_sdr.core.version",
                "CircuitState": "cja_auto_sdr.core.config",
            },
        )
        version = getter("__version__")
        assert isinstance(version, str)

        circuit_state = getter("CircuitState")
        assert hasattr(circuit_state, "CLOSED")

    def test_mapping_overrides_target_module(self):
        """When both mapping and target_module given, mapping takes precedence."""
        getter = make_getattr(
            "test_module",
            ["CircuitState"],
            target_module="cja_auto_sdr.core.version",  # wrong module
            mapping={"CircuitState": "cja_auto_sdr.core.config"},  # correct module
        )
        result = getter("CircuitState")
        assert hasattr(result, "CLOSED")

    def test_export_names_accepts_list(self):
        """make_getattr accepts a list for export_names."""
        getter = make_getattr(
            "test_module",
            ["__version__"],
            target_module="cja_auto_sdr.core.version",
        )
        assert callable(getter)

    def test_export_names_accepts_set(self):
        """make_getattr accepts a set for export_names."""
        getter = make_getattr(
            "test_module",
            {"__version__"},
            target_module="cja_auto_sdr.core.version",
        )
        result = getter("__version__")
        assert isinstance(result, str)

    def test_export_names_accepts_tuple(self):
        """make_getattr accepts a tuple for export_names."""
        getter = make_getattr(
            "test_module",
            ("__version__",),
            target_module="cja_auto_sdr.core.version",
        )
        result = getter("__version__")
        assert isinstance(result, str)

    def test_error_message_includes_module_name(self):
        """AttributeError message includes the module name for diagnostics."""
        getter = make_getattr(
            "my.custom.module",
            ["x"],
            target_module="cja_auto_sdr.core.version",
        )
        with pytest.raises(AttributeError, match=r"my\.custom\.module"):
            getter("unknown")


# ---------------------------------------------------------------------------
# Section 2: Parametrized tests for all forwarding modules
# ---------------------------------------------------------------------------

# Each tuple: (module_path, attribute_name)
# We pick one or two representative attributes per module to keep tests fast.

POSITIVE_CASES = [
    # Root package -> generator
    ("cja_auto_sdr", "__version__"),
    ("cja_auto_sdr", "main"),
    # core -> various submodules (lazy)
    ("cja_auto_sdr.core", "JSONFormatter"),
    ("cja_auto_sdr.core", "setup_logging"),
    ("cja_auto_sdr.core", "PerformanceTracker"),
    ("cja_auto_sdr.core", "ConfigValidator"),
    ("cja_auto_sdr.core", "CredentialResolver"),
    ("cja_auto_sdr.core", "LockManager"),
    ("cja_auto_sdr.core", "get_profiles_dir"),
    # core/profiles -> generator
    ("cja_auto_sdr.core.profiles", "get_profiles_dir"),
    ("cja_auto_sdr.core.profiles", "resolve_active_profile"),
    ("cja_auto_sdr.core.profiles", "validate_profile_name"),
    # api -> various submodules
    ("cja_auto_sdr.api", "configure_cjapy"),
    ("cja_auto_sdr.api", "initialize_cja"),
    ("cja_auto_sdr.api", "validate_data_view"),
    ("cja_auto_sdr.api", "ParallelAPIFetcher"),
    ("cja_auto_sdr.api", "ValidationCache"),
    ("cja_auto_sdr.api", "SharedValidationCache"),
    ("cja_auto_sdr.api", "APIWorkerTuner"),
    # cli -> generator
    ("cja_auto_sdr.cli", "main"),
    ("cja_auto_sdr.cli", "parse_arguments"),
    # cli/commands -> generator
    ("cja_auto_sdr.cli.commands", "generate_sample_config"),
    ("cja_auto_sdr.cli.commands", "list_dataviews"),
    ("cja_auto_sdr.cli.commands", "show_config_status"),
    ("cja_auto_sdr.cli.commands", "validate_config_only"),
    # data -> generator
    ("cja_auto_sdr.data", "ProcessingResult"),
    ("cja_auto_sdr.data", "DiffSummary"),
    # git -> generator (via diff.git)
    ("cja_auto_sdr.git", "is_git_repository"),
    ("cja_auto_sdr.git", "generate_git_commit_message"),
    # diff -> diff.writers
    ("cja_auto_sdr.diff", "write_diff_output"),
    ("cja_auto_sdr.diff", "write_diff_json_output"),
    ("cja_auto_sdr.diff", "write_diff_excel_output"),
    # org -> org.analyzer
    ("cja_auto_sdr.org", "OrgComponentAnalyzer"),
    # inventory -> inventory.summary
    ("cja_auto_sdr.inventory", "display_inventory_summary"),
    # pipeline package + modules -> generator
    ("cja_auto_sdr.pipeline", "BatchProcessor"),
    ("cja_auto_sdr.pipeline", "ProcessingResult"),
    ("cja_auto_sdr.pipeline", "process_single_dataview"),
    ("cja_auto_sdr.pipeline", "process_single_dataview_worker"),
    ("cja_auto_sdr.pipeline", "run_dry_run"),
    ("cja_auto_sdr.pipeline.batch", "BatchProcessor"),
    ("cja_auto_sdr.pipeline.dry_run", "run_dry_run"),
    ("cja_auto_sdr.pipeline.models", "ProcessingResult"),
    ("cja_auto_sdr.pipeline.single", "process_single_dataview"),
    ("cja_auto_sdr.pipeline.workers", "process_single_dataview_worker"),
]


@pytest.mark.parametrize(
    ("module_path", "attr_name"),
    POSITIVE_CASES,
    ids=[f"{m}.{a}" for m, a in POSITIVE_CASES],
)
def test_lazy_forward_resolves(module_path, attr_name):
    """Verify that each lazy-forwarded attribute resolves to a real object."""
    mod = importlib.import_module(module_path)
    result = getattr(mod, attr_name)
    assert result is not None


# Negative cases: each module should raise AttributeError for unknown attrs.

NEGATIVE_MODULES = [
    "cja_auto_sdr",
    "cja_auto_sdr.core",
    "cja_auto_sdr.core.profiles",
    "cja_auto_sdr.api",
    "cja_auto_sdr.cli",
    "cja_auto_sdr.cli.commands",
    "cja_auto_sdr.data",
    "cja_auto_sdr.output",
    "cja_auto_sdr.git",
    "cja_auto_sdr.diff",
    "cja_auto_sdr.org",
    "cja_auto_sdr.inventory",
    "cja_auto_sdr.pipeline",
    "cja_auto_sdr.pipeline.batch",
    "cja_auto_sdr.pipeline.dry_run",
    "cja_auto_sdr.pipeline.models",
    "cja_auto_sdr.pipeline.single",
    "cja_auto_sdr.pipeline.workers",
]


@pytest.mark.parametrize("module_path", NEGATIVE_MODULES, ids=NEGATIVE_MODULES)
def test_lazy_forward_rejects_unknown(module_path):
    """Verify that unknown attributes raise AttributeError, not silently resolve."""
    mod = importlib.import_module(module_path)
    with pytest.raises(AttributeError):
        getattr(mod, "__nonexistent_test_attr_xyz__")


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_small_module_coverage.py)
# ---------------------------------------------------------------------------


class TestMakeGetattrLazyTargetMissing:
    """Cover line 36: name in export_set but not in mapping."""

    def test_name_in_export_set_not_in_mapping(self):
        """Line 36: export name exists but has no mapping target."""
        getattr_fn = make_getattr(
            "test_module",
            ["foo", "bar"],
            mapping={"foo": "os"},
        )
        with pytest.raises(AttributeError, match="lazy target missing"):
            getattr_fn("bar")

    def test_name_not_in_export_set(self):
        """Line 37: name not in export_set at all."""
        getattr_fn = make_getattr("test_module", ["foo"], target_module="os")
        with pytest.raises(AttributeError, match="has no attribute"):
            getattr_fn("nonexistent")
