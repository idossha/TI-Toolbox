---
layout: wiki
title: Logging Processes in the Toolbox
permalink: /wiki/logging/
---

The TI-Toolbox logging system (`tit/logger.py`) is intentionally minimal. It configures the `tit` logger hierarchy but adds **no handlers by default** -- no console output, no file output -- until you explicitly attach one. This keeps terminal output clean and gives each entry point full control over where logs go.

## Architecture

The logging module exposes three public functions:

| Function | Purpose |
|----------|---------|
| `setup_logging(level)` | Set log level on the `tit` logger; adds NO handlers |
| `add_file_handler(log_file)` | Attach a `FileHandler` to a named logger |
| `get_file_only_logger(name, log_file)` | Return a standalone logger that writes only to a file |

### `setup_logging(level)`

```python
from tit.logger import setup_logging

setup_logging("DEBUG")
```

This does three things:
1. Clears any existing handlers on the `tit` logger
2. Sets the log level (defaults to `INFO`)
3. Sets `propagate = False` so messages never bubble to the root logger or terminal

Third-party loggers (`matplotlib`, `PIL`) are silenced to `ERROR` level.

### `add_file_handler(log_file, level, logger_name)`

```python
from tit.logger import add_file_handler

fh = add_file_handler("/path/to/run.log", level="DEBUG", logger_name="tit")
```

- Creates the parent directory if needed
- Opens the file in append mode
- Returns the `FileHandler` so callers can remove it when finished

### `get_file_only_logger(name, log_file)`

```python
from tit.logger import get_file_only_logger

logger = get_file_only_logger("tit.analyzer.roi", "/path/to/roi.log")
```

Returns a logger with `propagate = False` that writes exclusively to the given file. Useful for per-ROI or per-subject log isolation.

## Log Format

All file handlers use the same format:

```
2025-06-05 23:10:26 | INFO | tit.analyzer | Mesh analyzer initialized successfully
```

Fields: timestamp, level, logger name, message.

### Log Levels

- **DEBUG**: Detailed diagnostic information (file handlers default to this)
- **INFO**: General progress information
- **WARNING**: Potentially problematic situations
- **ERROR**: Serious problems
- **CRITICAL**: Fatal errors

## How Each Entry Point Uses Logging

### GUI (`tit/gui/`)

The GUI uses a custom `_QtHandler(logging.Handler)` that bridges log records to a Qt signal. This feeds log messages into the console widget of each tab without any terminal output.

### `__main__.py` Subprocess Entry Points

Modules invoked as subprocesses (`simnibs_python -m tit.analyzer config.json`) use `print()` for progress output. This is intentional: `BaseProcessThread` in the GUI captures stdout from subprocesses and displays it in the console widget. A stdlib logger with a `StreamHandler(sys.stdout)` is used in some entry points (e.g., `tit.sim.__main__`) for structured output that still reaches the GUI.

### Library Usage

When using `tit` as a library, call `setup_logging()` at your entry point and attach handlers as needed:

```python
from tit.logger import setup_logging, add_file_handler

setup_logging("INFO")
fh = add_file_handler("my_analysis.log")

# ... run analysis ...

# Clean up when done
import logging
logging.getLogger("tit").removeHandler(fh)
```

## What Was Removed

Previous versions (~v2.2.3 and earlier) had ~750 lines of custom logging infrastructure including:

- `get_logger()` factory function (deleted)
- `configure_external_loggers()` for SimNIBS integration
- Dual console + file output by default
- `TI_LOG_FILE`, `PROJECT_DIR`, `SUBJECT_ID` environment variables
- Debug toggles in the GUI

All of this has been replaced by the three functions described above. There are no environment variables and no debug toggles.

## Best Practices

1. **Call `setup_logging()` once** at your entry point -- not in library code
2. **Use `add_file_handler()`** to direct logs to a file when you need a record
3. **Use `print()`** in `__main__.py` modules where output must reach subprocess capture
4. **Use `logging.getLogger("tit.your_module")`** in library modules -- the hierarchy propagates to whatever handlers are attached to the `tit` logger
5. **Clean up handlers** when a run completes to avoid leaking file descriptors
