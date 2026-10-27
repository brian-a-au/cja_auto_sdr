"""Console colors and formatting utilities for CJA Auto SDR.

Provides ANSI color codes for terminal output with auto-detection
of TTY support and Windows compatibility.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import ClassVar

from cja_auto_sdr.core.error_policies import RECOVERABLE_OPEN_FILE_EXCEPTIONS


class ConsoleColors:
    """ANSI color codes for terminal output.

    Auto-detects TTY support and handles Windows compatibility.
    Use this class for general CLI output formatting.

    Supports multiple color themes for accessibility:
    - default: Green/red (standard)
    - accessible: Blue/orange (deuteranopia/protanopia friendly)
    """

    # Base colors
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    ORANGE = "\033[38;5;208m"  # Extended 256-color orange
    BOLD = "\033[1m"
    DIM = "\033[90m"  # Bright black / dark gray for dimmed text
    RESET = "\033[0m"
    # Regex to strip ANSI escape codes for visible length calculation
    ANSI_ESCAPE = re.compile(r"\033\[[0-9;]*m")

    # Color themes for accessibility
    THEMES: ClassVar[dict[str, dict[str, str]]] = {
        "default": {
            "added": GREEN,  # Green for additions
            "removed": RED,  # Red for removals
            "modified": YELLOW,  # Yellow for modifications
        },
        "accessible": {
            "added": BLUE,  # Blue for additions (accessible)
            "removed": ORANGE,  # Orange for removals (accessible)
            "modified": CYAN,  # Cyan for modifications
        },
    }

    # Current theme (default)
    _theme = "default"

    # Disable colors if not a TTY or on Windows without ANSI support
    _enabled = False

    @classmethod
    def _detect_default_enabled(cls) -> bool:
        """Detect whether ANSI colors should be enabled by default."""
        return sys.stdout.isatty() and (os.name != "nt" or os.environ.get("TERM"))

    @classmethod
    def configure(cls, no_color: bool = False) -> bool:
        """Configure color output from CLI/env policy and return final state.

        Priority:
        1. --no-color flag (always disable)
        2. FORCE_COLOR env var (non-empty and != "0" enables; "0" disables)
        3. NO_COLOR env var (non-empty disables)
        4. TTY auto-detection fallback
        """
        force_color_raw = os.environ.get("FORCE_COLOR")
        no_color_env = os.environ.get("NO_COLOR")

        if no_color:
            enabled = False
        elif force_color_raw is not None:
            enabled = force_color_raw.strip() not in ("", "0")
        elif no_color_env is not None and no_color_env.strip() != "":
            enabled = False
        else:
            enabled = cls._detect_default_enabled()

        cls._enabled = enabled
        return enabled

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        """Explicitly enable or disable ANSI colors."""
        cls._enabled = bool(enabled)

    @classmethod
    def set_theme(cls, theme: str) -> None:
        """Set the color theme. Valid themes: default, accessible"""
        if theme in cls.THEMES:
            cls._theme = theme
        else:
            raise ValueError(f"Unknown theme: {theme}. Valid themes: {', '.join(cls.THEMES.keys())}")

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if colors are enabled."""
        return cls._enabled

    @classmethod
    def success(cls, text: str) -> str:
        """Format text as success (green)"""
        if cls._enabled:
            return f"{cls.GREEN}{text}{cls.RESET}"
        return text

    # Alias for compatibility with ANSIColors
    green = success

    @classmethod
    def error(cls, text: str) -> str:
        """Format text as error (red)"""
        if cls._enabled:
            return f"{cls.RED}{text}{cls.RESET}"
        return text

    # Alias for compatibility with ANSIColors
    red = error

    @classmethod
    def warning(cls, text: str) -> str:
        """Format text as warning (yellow)"""
        if cls._enabled:
            return f"{cls.YELLOW}{text}{cls.RESET}"
        return text

    # Alias for compatibility with ANSIColors
    yellow = warning

    @classmethod
    def info(cls, text: str) -> str:
        """Format text as info (cyan)"""
        if cls._enabled:
            return f"{cls.CYAN}{text}{cls.RESET}"
        return text

    # Alias for compatibility with ANSIColors
    cyan = info

    @classmethod
    def bold(cls, text: str) -> str:
        """Format text as bold"""
        if cls._enabled:
            return f"{cls.BOLD}{text}{cls.RESET}"
        return text

    @classmethod
    def dim(cls, text: str) -> str:
        """Format text as dim/gray"""
        if cls._enabled:
            return f"{cls.DIM}{text}{cls.RESET}"
        return text

    @classmethod
    def status(cls, success: bool, text: str) -> str:
        """Format text based on success/failure status"""
        return cls.success(text) if success else cls.error(text)

    @classmethod
    def diff_added(cls, text: str) -> str:
        """Format text for 'added' items (theme-aware)"""
        if cls._enabled:
            color = cls.THEMES[cls._theme]["added"]
            return f"{color}{text}{cls.RESET}"
        return text

    @classmethod
    def diff_removed(cls, text: str) -> str:
        """Format text for 'removed' items (theme-aware)"""
        if cls._enabled:
            color = cls.THEMES[cls._theme]["removed"]
            return f"{color}{text}{cls.RESET}"
        return text

    @classmethod
    def diff_modified(cls, text: str) -> str:
        """Format text for 'modified' items (theme-aware)"""
        if cls._enabled:
            color = cls.THEMES[cls._theme]["modified"]
            return f"{color}{text}{cls.RESET}"
        return text

    @classmethod
    def visible_len(cls, text: str) -> int:
        """Return the visible length of a string, ignoring ANSI escape codes."""
        return len(cls.ANSI_ESCAPE.sub("", text))

    @classmethod
    def rjust(cls, text: str, width: int) -> str:
        """Right-justify a string accounting for ANSI escape codes."""
        visible = cls.visible_len(text)
        padding = max(0, width - visible)
        return " " * padding + text

    @classmethod
    def ljust(cls, text: str, width: int) -> str:
        """Left-justify a string accounting for ANSI escape codes."""
        visible = cls.visible_len(text)
        padding = max(0, width - visible)
        return text + " " * padding


# Alias for backwards compatibility
ANSIColors = ConsoleColors


# Initialize default color state at import time.
ConsoleColors.configure()


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable string (e.g., "1.5 MB", "256 KB", "42 B")
    """
    size = size_bytes
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def open_file_in_default_app(file_path: str | Path) -> bool:
    """
    Open a file in the default application for its type.

    Works cross-platform (macOS, Linux, Windows).

    Args:
        file_path: Path to the file to open

    Returns:
        True if successful, False otherwise
    """
    import logging
    import platform
    import subprocess
    import webbrowser

    file_path = str(file_path)
    logger = logging.getLogger(__name__)
    try:
        system = platform.system()
        if system == "Darwin":  # macOS
            subprocess.run(["open", file_path], check=True)
        elif system == "Windows":
            os.startfile(file_path)  # type: ignore[attr-defined]
        else:  # Linux and others
            subprocess.run(["xdg-open", file_path], check=True)
        return True
    except RECOVERABLE_OPEN_FILE_EXCEPTIONS as e:
        logger.debug(f"Failed to open file with default app: {file_path} - {e}")
        # Fallback to webbrowser for HTML files
        if file_path.endswith(".html"):
            try:
                webbrowser.open(f"file://{os.path.abspath(file_path)}")
                return True
            except RECOVERABLE_OPEN_FILE_EXCEPTIONS as e2:
                logger.debug(f"Fallback webbrowser.open also failed: {e2}")
        return False


def _format_error_msg(operation: str, item_type: str | None = None, error: Exception | None = None) -> str:
    """
    Format error messages consistently across the application.

    Args:
        operation: Description of the operation that failed (e.g., "checking duplicates")
        item_type: Optional item type context (e.g., "Metrics", "Dimensions")
        error: Optional exception to include in the message

    Returns:
        Formatted error message string
    """
    msg = f"Error {operation}"
    if item_type:
        msg += f" for {item_type}"
    if error:
        msg += f": {error!s}"
    return msg
