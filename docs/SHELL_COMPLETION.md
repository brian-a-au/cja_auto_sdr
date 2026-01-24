# Shell Completion Guide

Enable tab-completion for the `cja_auto_sdr` command in your terminal for faster, error-free command entry.

## Overview

Shell completion allows you to:
- Press `TAB` to auto-complete command options (e.g., `--fo` → `--format`)
- See available choices for options (e.g., `--format ` + `TAB` shows all formats)
- Reduce typos and speed up your workflow

## Quick Setup

### Bash

Add to your `~/.bashrc` or `~/.bash_profile`:

```bash
# Enable cja_auto_sdr tab completion
eval "$(register-python-argcomplete cja_auto_sdr)"
```

Then reload your shell:
```bash
source ~/.bashrc
```

### Zsh

Add to your `~/.zshrc`:

```zsh
# Enable cja_auto_sdr tab completion
autoload -U bashcompinit
bashcompinit
eval "$(register-python-argcomplete cja_auto_sdr)"
```

Then reload your shell:
```zsh
source ~/.zshrc
```

### Fish

Create a completion file:

```fish
# Create completions directory if needed
mkdir -p ~/.config/fish/completions

# Generate Fish completions
register-python-argcomplete --shell fish cja_auto_sdr > ~/.config/fish/completions/cja_auto_sdr.fish
```

Restart Fish or run:
```fish
source ~/.config/fish/completions/cja_auto_sdr.fish
```

## Prerequisites

The `argcomplete` package must be installed. It's included as an optional dependency:

```bash
# If using uv
uv add argcomplete

# If using pip
pip install argcomplete
```

Verify installation:
```bash
which register-python-argcomplete
# Should output a path like /usr/local/bin/register-python-argcomplete
```

## Usage Examples

Once configured, try these:

```bash
# Complete option names
cja_auto_sdr --for[TAB]
# Completes to: --format

# See available format choices
cja_auto_sdr --format [TAB][TAB]
# Shows: excel  csv  json  html  markdown  all  reports  data  ci

# Complete long options
cja_auto_sdr --val[TAB]
# Completes to: --validate-config

# Complete after partial input
cja_auto_sdr --log-[TAB][TAB]
# Shows: --log-level  --log-format
```

## Global Activation (Optional)

Instead of adding eval statements to each shell config, you can activate completions globally:

### Bash (Global)

```bash
# Run once (requires sudo)
sudo activate-global-python-argcomplete
```

This adds completion to `/etc/bash_completion.d/`.

### Per-User Activation

```bash
# Create user completion directory
mkdir -p ~/.bash_completion.d

# Add to ~/.bashrc
if [ -d ~/.bash_completion.d ]; then
    for f in ~/.bash_completion.d/*; do
        source "$f"
    done
fi

# Generate completion script
register-python-argcomplete cja_auto_sdr > ~/.bash_completion.d/cja_auto_sdr
```

## Troubleshooting

### Completions Not Working

1. **Verify argcomplete is installed:**
   ```bash
   python -c "import argcomplete; print('OK')"
   ```

2. **Check registration command exists:**
   ```bash
   which register-python-argcomplete
   ```

3. **Ensure shell config is sourced:**
   ```bash
   # Bash
   source ~/.bashrc

   # Zsh
   source ~/.zshrc
   ```

4. **Try direct evaluation:**
   ```bash
   eval "$(register-python-argcomplete cja_auto_sdr)"
   cja_auto_sdr --[TAB]
   ```

### "command not found: register-python-argcomplete"

The `argcomplete` package isn't installed or isn't in your PATH:

```bash
# Install argcomplete
pip install argcomplete

# Or if using the project's virtual environment
cd /path/to/cja_auto_sdr
uv add argcomplete
```

### Zsh: "command not found: compdef"

Add these lines before the eval statement in `~/.zshrc`:

```zsh
autoload -U compinit
compinit
autoload -U bashcompinit
bashcompinit
```

### Completions Work in Activated Venv Only

If completions only work when the virtual environment is activated, use the full path:

```bash
eval "$(register-python-argcomplete /path/to/cja_auto_sdr/.venv/bin/cja_auto_sdr)"
```

Or use `uv run` in the eval:
```bash
eval "$(cd /path/to/cja_auto_sdr && uv run register-python-argcomplete cja_auto_sdr)"
```

## PowerShell / Windows

`argcomplete` does not natively support PowerShell. On Windows, consider:

1. **Use WSL (Windows Subsystem for Linux)** - Full bash completion support
2. **Use Git Bash** - Bash completion works after setup
3. **Manual completion** - Use `cja_auto_sdr --help` to see available options

## See Also

- [CLI Reference](CLI_REFERENCE.md) - Complete list of all options
- [Quick Reference](QUICK_REFERENCE.md) - Common commands cheat sheet
- [argcomplete documentation](https://github.com/kislyuk/argcomplete)
