# Auto Search Python Error

Auto Search Python Error is a small console utility that scans a Python project, finds potential problems, and suggests improvements.

## Files

- `menu.py` - starts the menu and lets you choose what to check.
- `check_python_code.py` - checks regular Python code.
- `check_telegram_bots.py` - checks Telegram bot code.
- `core_analyzer.py` - shared logic for scanning files and generating reports.

## What it checks

### General Python check

- syntax errors
- mutable default arguments
- broad `except` blocks
- silent exception handling with `pass`
- `eval` and `exec`
- wildcard imports
- long functions and large files
- long lines
- TODO/FIXME/HACK markers

### Telegram bot check

- all common Python checks
- hardcoded Telegram tokens
- suspicious token variables stored in code
- `requests` calls without `timeout`
- direct Telegram API calls without visible timeout
- `while True` loops in bot code
- `print` usage instead of logging

## Run

```bash
python menu.py
```

Then choose:

1. regular Python code
2. Telegram bots
3. both checks
4. exit

Reports are saved to the `reports` folder automatically.
