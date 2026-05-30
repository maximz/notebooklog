# notebooklog

[![](https://img.shields.io/pypi/v/notebooklog.svg)](https://pypi.python.org/pypi/notebooklog)
[![CI](https://github.com/maximz/notebooklog/actions/workflows/ci.yaml/badge.svg?branch=master)](https://github.com/maximz/notebooklog/actions/workflows/ci.yaml)
[![](https://img.shields.io/badge/docs-here-blue.svg)](https://notebooklog.maximz.com)
[![](https://img.shields.io/github/stars/maximz/notebooklog?style=social)](https://github.com/maximz/notebooklog)

`notebooklog` is a small Python helper for capturing notebook or script output in
a log file without hiding it from the user. It configures Python logging and also
copies direct `stdout`/`stderr` writes, so messages from `print`, uncaught tracebacks,
warnings, and regular loggers can land in the same timestamped file.

The package is intended for long-running notebooks and scripts where the visible
session output is useful in the moment, but a durable record is needed afterward.

## Installation

```bash
pip install notebooklog
```

`notebooklog` supports Python 3.8+ and depends on `ipynbname` and
`python-slugify`.

## Usage

```python
import logging
from pathlib import Path

from notebooklog import setup_logger

logger, log_path = setup_logger(
    Path("logs"),
    name="analysis-run",
    log_level=logging.INFO,
)

logger.info("Starting analysis")
print("Printed output is copied to the same log file")

print(f"Writing log to {log_path}")
```

`setup_logger()` returns a named child logger plus the path to the log file it
created. If `name` is omitted, the package tries to infer one from the current
Jupyter notebook, the `HEADLESS_NOTEBOOK_NAME` environment variable, the running
script filename, or a fallback name for interactive sessions.

## How it works

Calling `setup_logger(log_dir, name=None, log_level=logging.INFO)`:

- creates `log_dir` if it does not already exist;
- creates a UTC timestamped log file named like
  `YYYYMMDD_HH-MM-SS.<slugified-name>.log`;
- configures the root logger with a formatted `stderr` handler at the requested
  log level;
- enables `logging.captureWarnings(True)`;
- copies direct `stdout` and `stderr` writes into the log file.

In a normal Python process, `sys.stdout` and `sys.stderr` are wrapped with a
pass-through stream that writes to both the original stream and the log file. In
a Jupyter notebook, the package leaves the active notebook streams in place and
attaches file writers through their `echo` hooks so later cell output is still
shown in the correct cell.

## Important behavior

`setup_logger()` changes process-wide logging and standard stream state. Call it
once near the start of a notebook or script; repeated calls add more root logging
handlers and can duplicate formatted log messages.

The log directory is created with `Path.mkdir(exist_ok=True)`, so parent
directories must already exist. The package exposes an importable API only; it
does not define a command-line interface.

## Development

```bash
pip install -r requirements_dev.txt
pip install -e .
make test
make lint
make docs
```

The repository also includes Sphinx documentation configuration, GitHub Actions
CI, coverage settings, and packaging metadata for building and publishing the
Python package.
