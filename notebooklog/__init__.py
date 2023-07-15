"""
Logging for Jupyter notebooks and scripts alike:

Create a logger for main application (e.g. current notebook) and configure writing to file as well.

This will capture any direct stdout/stderr writes that didn't come from a logger, too.
"""

__author__ = """Maxim Zaslavsky"""
__email__ = "maxim@maximz.com"
__version__ = "0.0.2"


import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple
import io

from slugify import slugify


def setup_logger(
    log_dir: Path, name: Optional[str] = None, log_level: int = logging.INFO
) -> Tuple[logging.Logger, Path]:
    """
    Configure root logger to write to stdout/stderr, and also pipe stdout/stderr (including messages not issued by a logger) to a log file.
    Then returns a child logger for the main application that simply propagates to root logger with an application name attached.
    """

    if name is None:
        name = _get_main_application_name()

    # Set up log file.
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H-%M-%S")
    log_dir = Path(log_dir)  # defensive cast
    # create logging directory just in case
    log_dir.mkdir(exist_ok=True)
    # create log file name
    log_fname = log_dir / f"{timestamp}.{slugify(name)}.log"

    # Forward stdout/stderr to this log file.
    _forward_standard_streams_to_logger(log_fname)

    # Configure root logger to write to stderr with formatting.
    logger = logging.getLogger()
    consoleHandler = logging.StreamHandler(stream=sys.stderr)
    consoleHandler.setLevel(log_level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)

    # Set log level for all handlers to debug
    logger.setLevel(log_level)

    # Capture warnings in logs: https://stackoverflow.com/a/37979724/130164
    logging.captureWarnings(True)

    # Create child logger for the main application (e.g. notebook) specifically
    main_application_logger = logging.getLogger(name)
    return main_application_logger, log_fname


class ForwardStreamToFile:
    """Wrap streams like stdout/stderr to forward their messages to a file.

    *Usage in a script:*
    Replace stdout or stderr with a ForwardStreamToFile wrapper to write to a file before passing back through to the original output stream.

    *Usage in a notebook:*
    Register a ForwardStreamToFile to receive echoes from Jupyter's own wrapper of stdout/stderr, then write these echoes to a file.
    To receive echoes from Jupyter's wrapper, we must supply a file object: see https://github.com/ipython/ipykernel/blob/ae6836ff54c6b82e230ebc593b78d50ac470aed7/ipykernel/iostream.py#L286
    Jupyter verifies that it has a read(), but only calls write() and flush(). So ForwardStreamToFile is a mock file object that writes any input to the supplied log function.

    We could just use a direct file object for the log file here, but we add some customization of the writing behavior below. To prevent unnecessary new lines in logs, we buffer log messages until we see a newline character.
    (Pass-through to the original stdout/stderr stream continues in the meantime.)
    """

    # Must specify encoding for Click to play well with our redirected output streams.
    # TODO: consider inheritting from TextIOWrapper or TextIOBase? see click docs.
    encoding = "UTF-8"

    # See https://stackoverflow.com/a/31688396/130164
    # Alternative to consider: https://stackoverflow.com/a/616686/130164
    def __init__(
        self,
        file_object: io.TextIOWrapper,
        pass_through: Optional[io.TextIOWrapper] = None,
    ) -> None:
        """
        Wrap an output stream to intercept all messages and write them to a file.

        Parameters:
        - file_object: an open log file object to write to.
        - pass_through: supply a stream like stdout or stderr to write messages back to the stream after intercepting them.
        """
        self.file_object = file_object
        self.buffer = []
        self.pass_through = pass_through

    def read(self):
        # no-op
        # only here to make this look like a file object for Jupyter's OutStream to accept this for echoes
        pass

    def _emit_buffered(self) -> None:
        # If we have something buffered, write it out.
        if len(self.buffer) > 0:
            # Combine message
            full_message = "".join(self.buffer) + "\n"
            # Write to open file
            self.file_object.write(full_message)
            # Reset buffer
            self.buffer = []

    def write(self, message: str) -> None:
        # Reduce unnecessary newlines in messages
        # See https://stackoverflow.com/a/51612402/130164 and https://stackoverflow.com/a/66209331/130164

        if message.endswith("\n"):
            # Buffer the message
            self.buffer.append(message.rstrip("\n"))
            # Emit all buffered messages
            self._emit_buffered()
        else:
            # Buffer the message.
            self.buffer.append(message)

        if self.pass_through is not None:
            # Pass through to original stdout/err stream even if buffering writes to file
            self.pass_through.write(message)

    def flush(self) -> None:
        # Emit anything buffered, i.e. if there were any writes recently that did not have a \n at the end.
        self._emit_buffered()

        self.file_object.flush()

        if self.pass_through is not None:
            # Flush the pass-through stream.
            self.pass_through.flush()

    def close(self) -> None:
        self.flush()

    def isatty(self):
        # pytest checks file.isatty()
        # see https://github.com/pytest-dev/pytest/issues/1447#issuecomment-194676124
        if self.pass_through is not None:
            return self.pass_through.isatty()
        return self.file_object.isatty()


def _forward_standard_streams_to_logger(log_fname: Path) -> None:
    """
    Pass any direct stdout or stderr writes to our log file writer too.

    This handles several message flows:
    - User or library sends a log message -> propagates up to root logger -> root logger formats and writes the message to stderr stream -> stderr stream is actually a wrapper that appends to a log file before writing to the real stderr.
    - User or library writes directly to stderr (or stdout) -> stderr stream is actually a wrapper that appends to a log file before writing to the real stderr. (No actual logger is executed here.)

    (We considered adding a FileHandler to the logger directly and having the stream wrapper emit a log message, but this caused some messages to be formatted+logged twice, e.g. logger -> stderr -> logger.)
    """
    file_obj = open(log_fname, "a")
    if not _is_notebook():
        # Configure for non-notebooks.
        # This replaces sys.stdout and sys.stderr. To access the original stdout/stderr, can still use sys.__stdout__/sys.__stderr__
        # see https://stackoverflow.com/questions/14393989/per-cell-output-for-threaded-ipython-notebooks
        # see https://stackoverflow.com/questions/64572585/how-to-simultaneously-capture-and-display-ipython-jupyter-notebook-cell-output
        # see https://stackoverflow.com/questions/47778449/how-to-save-errors-from-jupyter-notebook-cells-to-a-file
        # Avoid this in notebooks, because this will write to stderr of the cell where logging is configured, not the cell producing an error.
        sys.stderr = ForwardStreamToFile(file_obj, pass_through=sys.__stderr__)
        sys.stdout = ForwardStreamToFile(file_obj, pass_through=sys.__stdout__)
    else:
        # Configure for notebooks.
        # In notebooks, sys.stdout and sys.stderr are already replaced by ipykernel.iostream.OutStream and change from cell to cell.
        # If we were to use the above replacement of sys.stdout/sys.stderr, we would not be getting updated streams to write to the right cell. We'd be writing to the stdout/stderr that belongs to another cell.
        # Instead: Configure the OutStream to also echo to our file-writer when it is called. See https://saturncloud.io/blog/long-running-notebooks/
        # (Echo requires a file object, so ForwardStreamToFile is designed to look like one.)
        sys.stderr.echo = ForwardStreamToFile(file_obj)
        sys.stdout.echo = ForwardStreamToFile(file_obj)


def _is_notebook() -> bool:
    # From https://stackoverflow.com/a/39662359/130164
    try:
        shell = get_ipython().__class__.__name__
        if shell == "ZMQInteractiveShell":
            return True  # Jupyter notebook or qtconsole
        elif shell == "TerminalInteractiveShell":
            return False  # Terminal running IPython
        else:
            return False  # Other type (?)
    except NameError:
        return False  # Probably standard Python interpreter


def _get_main_application_name() -> str:
    """Get main application name to identify it in logger."""
    if _is_notebook():
        # running a notebook.
        import ipynbname

        try:
            # try to get notebook name using https://github.com/msm1089/ipynbname
            return ipynbname.name() + ".iypnb"
        except:
            # ipynbname doesn't work if executing a notebook from command line.
            # To work around this, we set HEADLESS_NOTEBOOK_NAME environment variable in run_notebooks.sh.
            nb_fname = os.getenv("HEADLESS_NOTEBOOK_NAME", default=None)
            if nb_fname is not None:
                # HEADLESS_NOTEBOOK_NAME may be the full path to the notebook.
                # Extract just the file name.
                return os.path.basename(nb_fname)

            # Use a default name if HEADLESS_NOTEBOOK_NAME was not found.
            return "unknown(notebook)"

    # Check if interactive, from https://stackoverflow.com/a/22424821/130164
    import __main__ as main

    is_interactive = not hasattr(main, "__file__")
    if is_interactive:
        # at this point we know it's console, not notebook
        return "unknown(console)"

    # Not a notebook or console, so running a script.
    script_name = main.__file__
    if script_name is not None:
        return os.path.basename(script_name)

    script_name = __name__
    if script_name != "__main__":
        # TODO: Not sure if we need this - should be handled by main.__file__?
        return script_name

    # Couldn't tell - give a default answer.
    return "unknown"
