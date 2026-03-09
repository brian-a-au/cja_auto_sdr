"""CLI command handlers exposed via lazy forwarding."""

__all__ = [
    "describe_dataview",
    "generate_sample_config",
    "list_calculated_metrics",
    "list_connections",
    "list_datasets",
    "list_dataviews",
    "list_dimensions",
    "list_metrics",
    "list_segments",
    "show_config_status",
    "validate_config_only",
]

from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(
    __name__,
    __all__,
    mapping={
        "describe_dataview": "cja_auto_sdr.cli.commands.list",
        "generate_sample_config": "cja_auto_sdr.cli.commands.config",
        "list_calculated_metrics": "cja_auto_sdr.cli.commands.list",
        "list_connections": "cja_auto_sdr.cli.commands.list",
        "list_datasets": "cja_auto_sdr.cli.commands.list",
        "list_dataviews": "cja_auto_sdr.cli.commands.list",
        "list_dimensions": "cja_auto_sdr.cli.commands.list",
        "list_metrics": "cja_auto_sdr.cli.commands.list",
        "list_segments": "cja_auto_sdr.cli.commands.list",
        "show_config_status": "cja_auto_sdr.cli.commands.config",
        "validate_config_only": "cja_auto_sdr.cli.commands.config",
    },
)
