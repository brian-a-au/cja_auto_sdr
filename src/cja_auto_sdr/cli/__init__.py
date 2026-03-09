"""CLI module - Command-line interface components.

``parse_arguments`` lives in ``cli.parser`` (canonical implementation).
Other symbols are resolved lazily via ``__getattr__`` to avoid circular imports.
"""

from cja_auto_sdr.core.lazy import make_getattr

__all__ = [
    "generate_sample_config",
    "interactive_select_dataviews",
    "interactive_wizard",
    "list_dataviews",
    "main",
    "parse_arguments",
    "prompt_for_selection",
    "show_config_status",
    "validate_config_only",
]

__getattr__ = make_getattr(
    __name__,
    __all__,
    mapping={
        # Canonical implementation in cli.parser
        "parse_arguments": "cja_auto_sdr.cli.parser",
        # Remaining entrypoints
        "generate_sample_config": "cja_auto_sdr.cli.commands.config",
        "interactive_select_dataviews": "cja_auto_sdr.generator",
        "interactive_wizard": "cja_auto_sdr.generator",
        "list_dataviews": "cja_auto_sdr.cli.commands.list",
        "main": "cja_auto_sdr.generator",
        "prompt_for_selection": "cja_auto_sdr.generator",
        "show_config_status": "cja_auto_sdr.cli.commands.config",
        "validate_config_only": "cja_auto_sdr.cli.commands.config",
    },
)
