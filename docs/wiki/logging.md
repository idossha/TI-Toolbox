---
layout: wiki
title: Logging Processes in the Toolbox
permalink: /wiki/logging/
---

## Where are the logs

- **Per-run logs** — pre-processing and the optimizers write their own log files to
  `derivatives/ti-toolbox/logs/sub-<id>/` in your project.
- **Job consoles** — each job's full console is `code/ti-toolbox/jobs/<id>/stdout.log`; the job's
  **Raw log** tab shows all of it. The folder button beside a console opens the job's results
  folder (**Open output folder**), or the job's own folder when it has no results folder
  (**Open job folder**). Finished job records older than 30 days, or beyond the newest 200, are
  deleted when the server starts (see [Jobs]({{ site.baseurl }}/wiki/jobs/)).
- **The desktop app's own log** — `main.log`: on macOS `~/Library/Logs/TI-Toolbox/main.log`, on
  Windows `%APPDATA%\ti-toolbox-desktop\logs\main.log`, on Linux
  `${XDG_CONFIG_HOME:-~/.config}/ti-toolbox-desktop/logs/main.log`.

## The logging API

The TI-Toolbox logging system (`tit/logger.py`) is intentionally minimal. On import, `tit/__init__.py` auto-configures the `tit` logger hierarchy with a stdout handler at INFO level — no explicit setup is needed. File logging is opt-in via `add_file_handler()`.

## Architecture

The main scripting helpers are:

| Function | Purpose |
|----------|---------|
| `setup_logging(level)` | Set log level; attaches a JSON event handler when the server supplies `TIT_EVENTS_FILE` (called automatically on import) |
| `add_stream_handler(logger_name, level)` | Attach a stdout `StreamHandler` (called on import for `tit` at INFO) |
| `add_file_handler(log_file)` | Attach a `FileHandler` to a named logger |
| `get_file_only_logger(name, log_file)` | Return a standalone logger that writes only to a file |

### `setup_logging(level)`

Called automatically by `tit/__init__.py` on import. You only need to call it explicitly if you want to change the log level:

```python
from tit.logger import setup_logging

setup_logging("DEBUG")  # override the default INFO level
```

This does three things:
1. Clears any existing handlers on the `tit` logger
2. Sets the log level (defaults to `INFO`)
3. Sets `propagate = False` so messages never bubble to the root logger

Third-party loggers (`matplotlib`, `PIL`) are silenced to `ERROR` level. When `TIT_EVENTS_FILE` is set by the job runner, setup also attaches a JSON event handler to `tit` and `simnibs`; log records share the job’s ordered event stream with stage, progress, artifact and exit events.

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

### Desktop application

The desktop app streams job logs over the HTTP API (`tit.server`) rather than through an in-process logging handler; each job's output is written to its log file and relayed to the run page's terminal.

### `__main__.py` Subprocess Entry Points

Modules invoked as subprocesses (`simnibs_python -m tit.analyzer config.json`) write logs and progress from inside the container. The job runner captures stdout and stderr to the job log; structured events and logging records are streamed to the UI through the server.

### Library Usage

When using `tit` as a library, logging is auto-configured on import — no setup call needed. To add file logging, attach a handler:

```python
from tit import add_file_handler

fh = add_file_handler("my_analysis.log")

# ... run analysis ...

# Clean up when done
import logging
logging.getLogger("tit").removeHandler(fh)
```

## Best Practices

1. **Logging auto-initializes on import** — no explicit `setup_logging()` call needed
2. **Use `add_file_handler()`** to direct logs to a file when you need a record
3. **Use `print()`** in `__main__.py` modules where output must reach subprocess capture
4. **Use `logging.getLogger("tit.your_module")`** in library modules -- the hierarchy propagates to whatever handlers are attached to the `tit` logger
5. **Clean up handlers** when a run completes to avoid leaking file descriptors
