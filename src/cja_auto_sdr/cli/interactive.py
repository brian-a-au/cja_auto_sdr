"""Interactive CLI flows extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import sys

import pandas as pd

from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.constants import BANNER_WIDTH

__all__ = [
    "interactive_select_dataviews",
    "interactive_wizard",
    "prompt_for_selection",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def prompt_for_selection(options: list[tuple[str, str]], prompt_text: str) -> str | None:
    """Prompt the user to pick a single option from a numbered list."""
    if not sys.stdin.isatty():
        return None

    print(f"\n{prompt_text}")
    print("-" * 40)

    for index, (option_id, display) in enumerate(options, 1):
        print(f"  [{index}] {display}")
        print(f"      ID: {option_id}")

    print("  [0] Cancel")
    print()

    while True:
        try:
            choice = input("Enter selection (number): ").strip()
            if choice == "0" or choice.lower() in ("q", "quit", "cancel"):
                return None

            index = int(choice)
            if 1 <= index <= len(options):
                return options[index - 1][0]

            print(f"Invalid selection. Enter 1-{len(options)} or 0 to cancel.")
        except ValueError:
            print("Please enter a number.")
        except EOFError:
            print("\nCancelled.")
            return None
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None


def _parse_multi_selection(selection: str, item_count: int) -> tuple[list[int] | None, str | None]:
    """Parse interactive list selections like ``1,3-5`` or ``all``."""
    selected_indices: set[int] = set()

    if selection in ("all", "a", "*"):
        return list(range(1, item_count + 1)), None

    parts = selection.replace(" ", "").split(",")
    for part in parts:
        if not part:
            continue
        if "-" in part:
            try:
                range_parts = part.split("-")
                if len(range_parts) != 2:
                    raise ValueError("invalid range")
                start = int(range_parts[0])
                end = int(range_parts[1])
                if start > end:
                    start, end = end, start
                for index in range(start, end + 1):
                    selected_indices.add(index)
            except ValueError:
                return None, f"Invalid range: '{part}'. Use format like '1-5'."
        else:
            try:
                selected_indices.add(int(part))
            except ValueError:
                return None, f"Invalid number: '{part}'."

    invalid_indices = [index for index in selected_indices if index < 1 or index > item_count]
    if invalid_indices:
        return None, f"Invalid selection(s): {invalid_indices}. Valid range: 1-{item_count}"

    if not selected_indices:
        return None, "No valid selections. Please try again."

    return sorted(selected_indices), None


def interactive_select_dataviews(config_file: str = "config.json", profile: str | None = None) -> list[str]:
    """Interactively select one or more data views from the accessible list."""
    generator = _generator_module()

    print()
    print("=" * BANNER_WIDTH)
    print("INTERACTIVE DATA VIEW SELECTION")
    print("=" * BANNER_WIDTH)
    print()
    if profile:
        print(f"Using profile: {profile}")
    else:
        print(f"Using configuration: {config_file}")
    print()

    try:
        success, source, _ = generator.configure_cjapy(profile, config_file)
        if not success:
            print(ConsoleColors.error(f"ERROR: {source}"))
            return []
        cja = generator.cjapy.CJA()

        print("Fetching available data views...")
        available_dvs = cja.getDataViews()

        if available_dvs is None or (hasattr(available_dvs, "__len__") and len(available_dvs) == 0):
            print()
            print(ConsoleColors.warning("No data views found or no access to any data views."))
            return []

        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict("records")

        display_data = []
        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = generator._normalize_optional_text(dv.get("id"), default="N/A")
                dv_name = generator._normalize_optional_text(dv.get("name"), default="N/A")
                owner_name = generator._extract_owner_name(dv.get("owner"))
                display_data.append({"id": dv_id, "name": dv_name, "owner": owner_name})

        if not display_data:
            print(ConsoleColors.warning("No data views available."))
            return []

        num_width = len(str(len(display_data))) + 2
        max_id_width = max(len("ID"), *(len(item["id"]) for item in display_data)) + 2
        max_name_width = max(len("Name"), *(len(item["name"]) for item in display_data)) + 2
        max_owner_width = max(len("Owner"), *(len(item["owner"]) for item in display_data)) + 2
        total_width = num_width + max_id_width + max_name_width + max_owner_width

        print()
        print(f"Found {len(display_data)} accessible data view(s):")
        print()
        print(f"{'#':<{num_width}} {'ID':<{max_id_width}} {'Name':<{max_name_width}} {'Owner':<{max_owner_width}}")
        print("-" * total_width)

        for index, item in enumerate(display_data, 1):
            print(
                f"{index:<{num_width}} {item['id']:<{max_id_width}} {item['name']:<{max_name_width}} {item['owner']:<{max_owner_width}}",
            )

        print()
        print("-" * total_width)
        print("Selection options:")
        print("  Single:   3         (selects #3)")
        print("  Multiple: 1,3,5     (selects #1, #3, #5)")
        print("  Range:    1-5       (selects #1 through #5)")
        print("  Combined: 1,3-5,7   (selects #1, #3, #4, #5, #7)")
        print("  All:      all or a  (selects all data views)")
        print("  Cancel:   q or quit (exit without selection)")
        print()

        while True:
            try:
                selection = input("Enter selection: ").strip().lower()
            except EOFError:
                print()
                print(ConsoleColors.warning("No input available (non-interactive terminal)."))
                return []

            if not selection:
                print("Please enter a selection.")
                continue

            if selection in ("q", "quit", "exit", "cancel"):
                print(ConsoleColors.warning("Selection cancelled."))
                return []

            selected_indices, error_message = _parse_multi_selection(selection, len(display_data))
            if error_message:
                if error_message.startswith(("Invalid range", "Invalid number")):
                    print(ConsoleColors.error(error_message))
                else:
                    print(error_message)
                continue

            assert selected_indices is not None
            selected_ids = [display_data[index - 1]["id"] for index in selected_indices]

            print()
            print(f"Selected {len(selected_ids)} data view(s):")
            for index in selected_indices:
                item = display_data[index - 1]
                print(f"  {index}. {item['name']} ({item['id']})")

            return selected_ids

    except FileNotFoundError:
        print(ConsoleColors.error(f"ERROR: Configuration file '{config_file}' not found"))
        print()
        print("Generate a sample configuration file with:")
        print("  cja_auto_sdr --sample-config")
        return []
    except KeyboardInterrupt:
        print()
        print(ConsoleColors.warning("Operation cancelled."))
        return []
    except SystemExit:
        print()
        print(ConsoleColors.warning("Operation cancelled."))
        return []
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        print(ConsoleColors.error(f"ERROR: Failed to connect to CJA API: {e!s}"))
        return []


def interactive_wizard(config_file: str = "config.json", profile: str | None = None):
    """Guide the user through SDR generation with interactive prompts."""
    generator = _generator_module()

    def prompt_choice(prompt: str, options: list[tuple[str, str]], default: str | None = None) -> str | None:
        print()
        print(prompt)
        print()
        for index, (key, label) in enumerate(options, 1):
            default_marker = " (default)" if key == default else ""
            print(f"  {index}. {label}{default_marker}")
        print()
        print("  q. Cancel and exit")
        print()

        while True:
            try:
                default_hint = f" [{options[[k for k, _ in options].index(default)][1]}]" if default else ""
                choice = input(f"Enter choice (1-{len(options)}){default_hint}: ").strip().lower()
            except EOFError:
                print()
                return None
            except KeyboardInterrupt:
                print()
                return None

            if choice in ("q", "quit", "exit", "cancel"):
                return None
            if not choice and default:
                return default

            try:
                index = int(choice) - 1
                if 0 <= index < len(options):
                    return options[index][0]
                print(f"Please enter a number between 1 and {len(options)}.")
            except ValueError:
                print(f"Please enter a number between 1 and {len(options)}, or 'q' to cancel.")

    def prompt_yes_no(prompt: str, default: bool = False) -> bool | None:
        prompt_hint = "[Y/n] (Enter=yes)" if default else "[y/N] (Enter=no)"
        valid_yes = ("y", "yes", "1", "true")
        valid_no = ("n", "no", "0", "false")
        valid_quit = ("q", "quit", "exit", "cancel")

        while True:
            print()
            try:
                answer = input(f"{prompt} {prompt_hint}: ").strip().lower()
            except EOFError:
                print()
                return None
            except KeyboardInterrupt:
                print()
                return None

            if answer in valid_quit:
                return None
            if not answer:
                return default
            if answer in valid_yes:
                return True
            if answer in valid_no:
                return False

            print(ConsoleColors.warning(f"Invalid input '{answer}'. Please enter 'y' or 'n' (or 'q' to quit)."))

    print()
    print("=" * BANNER_WIDTH)
    print("  CJA SDR GENERATOR - INTERACTIVE MODE")
    print("=" * BANNER_WIDTH)
    print()
    print("This interactive mode will guide you through generating an SDR.")
    print("Press 'q' at any prompt to cancel.")

    print()
    print("-" * 60)
    print("STEP 1: Select Data View(s)")
    print("-" * 60)

    if profile:
        print(f"Using profile: {profile}")
    else:
        print(f"Using configuration: {config_file}")
    print()

    try:
        success, source, _ = generator.configure_cjapy(profile, config_file)
        if not success:
            print(ConsoleColors.error(f"ERROR: {source}"))
            return None
        cja = generator.cjapy.CJA()

        print("Fetching available data views...")
        available_dvs = cja.getDataViews()

        if available_dvs is None or (hasattr(available_dvs, "__len__") and len(available_dvs) == 0):
            print()
            print(ConsoleColors.warning("No data views found or no access to any data views."))
            return None

        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict("records")

        display_data = []
        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = generator._normalize_optional_text(dv.get("id"), default="N/A")
                dv_name = generator._normalize_optional_text(dv.get("name"), default="N/A")
                display_data.append({"id": dv_id, "name": dv_name})

        if not display_data:
            print(ConsoleColors.warning("No data views available."))
            return None

        print()
        print(f"Found {len(display_data)} accessible data view(s):")
        print()
        for index, item in enumerate(display_data, 1):
            print(f"  {index}. {item['name']}")
            print(f"      {ConsoleColors.dim(item['id'])}")

        print()
        print("Selection options: single (3), multiple (1,3,5), range (1-3), all")
        print()

        while True:
            try:
                selection = input("Select data view(s): ").strip().lower()
            except EOFError:
                print()
                return None
            except KeyboardInterrupt:
                print()
                return None

            if selection in ("q", "quit", "exit", "cancel"):
                print(ConsoleColors.warning("Cancelled."))
                return None
            if not selection:
                print("Please enter a selection.")
                continue

            selected_indices, error_message = _parse_multi_selection(selection, len(display_data))
            if error_message:
                print(ConsoleColors.error(error_message) if error_message.startswith("Invalid") else error_message)
                continue

            assert selected_indices is not None
            selected_ids = [display_data[index - 1]["id"] for index in selected_indices]
            selected_names = [display_data[index - 1]["name"] for index in selected_indices]

            print()
            print(f"Selected: {', '.join(selected_names)}")
            break

    except FileNotFoundError:
        print(ConsoleColors.error(f"ERROR: Configuration file '{config_file}' not found"))
        print("Run: cja_auto_sdr --sample-config")
        return None
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        print(ConsoleColors.error(f"ERROR: Failed to connect to CJA API: {e!s}"))
        return None

    print()
    print("-" * 60)
    print("STEP 2: Choose Output Format")
    print("-" * 60)

    format_options = [
        ("excel", "Excel (.xlsx) - Best for review and sharing"),
        ("json", "JSON - Best for automation and APIs"),
        ("csv", "CSV - Best for data processing"),
        ("html", "HTML - Best for web viewing"),
        ("markdown", "Markdown - Best for documentation/GitHub"),
        ("all", "All formats - Generate everything"),
    ]

    output_format = prompt_choice("Which output format would you like?", format_options, default="excel")
    if output_format is None:
        print(ConsoleColors.warning("Cancelled."))
        return None

    print()
    print("-" * 60)
    print("STEP 3: Include Inventory Data?")
    print("-" * 60)
    print()
    print("Inventory data provides additional documentation beyond the standard SDR:")
    print("  • Segments: Filter definitions, complexity scores, references")
    print("  • Calculated Metrics: Formulas, complexity, metric dependencies")
    print("  • Derived Fields: Logic analysis, functions used, schema references")

    include_segments = prompt_yes_no("Include Segments inventory?", default=False)
    if include_segments is None:
        print(ConsoleColors.warning("Cancelled."))
        return None

    include_calculated = prompt_yes_no("Include Calculated Metrics inventory?", default=False)
    if include_calculated is None:
        print(ConsoleColors.warning("Cancelled."))
        return None

    include_derived = prompt_yes_no("Include Derived Fields inventory?", default=False)
    if include_derived is None:
        print(ConsoleColors.warning("Cancelled."))
        return None

    print()
    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print()
    print(f"  Data View(s):        {', '.join(selected_names)}")
    print(f"  Output Format:       {output_format.upper()}")
    print(f"  Include Segments:    {'Yes' if include_segments else 'No'}")
    print(f"  Include Calc Metrics: {'Yes' if include_calculated else 'No'}")
    print(f"  Include Derived:     {'Yes' if include_derived else 'No'}")
    print()

    confirm = prompt_yes_no("Generate SDR with these settings?", default=True)
    if not confirm:
        print(ConsoleColors.warning("Cancelled."))
        return None

    return generator.WizardConfig(
        data_view_ids=selected_ids,
        output_format=output_format,
        include_segments=include_segments,
        include_calculated=include_calculated,
        include_derived=include_derived,
    )
