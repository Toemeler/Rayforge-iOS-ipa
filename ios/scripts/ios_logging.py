"""
ios_logging.py — On-device log capture for Rayforge iOS.

This module is bundled INTO the iOS app. When Rayforge starts on the iPad it
redirects Python's stdout/stderr and the logging framework into a persistent
log file inside the app's Documents directory, which is accessible from the
iOS Files app (and via Finder/iTunes file sharing when
UIFileSharingEnabled is set in Info.plist).

If anything crashes on device, the user can open the Files app, grab
`rayforge-ios.log`, and send it back for diagnosis.

Usage (called as early as possible in app startup, before importing gtk):
    from ios_logging import install_ios_logging
    install_ios_logging()
"""

import atexit
import datetime
import faulthandler
import logging
import os
import sys
import traceback

LOG_FILENAME = "rayforge-ios.log"


def _documents_dir() -> str:
    """
    Resolve the iOS app Documents directory.

    On iOS, ~ expands to the app sandbox home; Documents is the standard
    user-visible, file-sharing-exposed location. Falls back to the sandbox
    home or cwd if for some reason Documents cannot be created.
    """
    candidates = [
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~"),
        os.getcwd(),
    ]
    for base in candidates:
        try:
            os.makedirs(base, exist_ok=True)
            testpath = os.path.join(base, ".rayforge_write_test")
            with open(testpath, "w") as fh:
                fh.write("ok")
            os.remove(testpath)
            return base
        except Exception:
            continue
    return os.getcwd()


class _Tee:
    """Write to both the original stream and the log file."""

    def __init__(self, original, logfile):
        self._original = original
        self._logfile = logfile

    def write(self, data):
        try:
            if self._original is not None:
                self._original.write(data)
        except Exception:
            pass
        try:
            self._logfile.write(data)
            self._logfile.flush()
        except Exception:
            pass

    def flush(self):
        for s in (self._original, self._logfile):
            try:
                if s is not None:
                    s.flush()
            except Exception:
                pass


_log_file_handle = None
_log_path = None


def install_ios_logging(level=logging.DEBUG) -> str:
    """
    Install the on-device logging facility. Returns the log file path.

    Safe to call multiple times; only the first call installs.
    """
    global _log_file_handle, _log_path
    if _log_file_handle is not None:
        return _log_path

    docs = _documents_dir()
    _log_path = os.path.join(docs, LOG_FILENAME)

    # Open in append mode so logs from multiple sessions accumulate.
    _log_file_handle = open(_log_path, "a", buffering=1, encoding="utf-8")

    header = (
        "\n"
        "==================================================================\n"
        f" Rayforge iOS session start: {datetime.datetime.now().isoformat()}\n"
        f" Python: {sys.version}\n"
        f" Platform: {sys.platform}\n"
        f" Executable: {sys.executable}\n"
        f" Log path: {_log_path}\n"
        "==================================================================\n"
    )
    _log_file_handle.write(header)
    _log_file_handle.flush()

    # 1. Tee stdout/stderr into the log file.
    sys.stdout = _Tee(sys.__stdout__, _log_file_handle)
    sys.stderr = _Tee(sys.__stderr__, _log_file_handle)

    # 2. Route the logging framework into the same file.
    root = logging.getLogger()
    root.setLevel(level)
    fh = logging.StreamHandler(_log_file_handle)
    fh.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # 3. Faulthandler: dump native/Python tracebacks on hard crashes
    #    (segfaults in the GTK/native layer) directly into the log.
    try:
        faulthandler.enable(file=_log_file_handle, all_threads=True)
    except Exception:
        pass

    # 4. Catch otherwise-unhandled Python exceptions.
    def _excepthook(exc_type, exc_value, exc_tb):
        _log_file_handle.write("\n===== UNHANDLED EXCEPTION =====\n")
        traceback.print_exception(
            exc_type, exc_value, exc_tb, file=_log_file_handle
        )
        _log_file_handle.flush()
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # 5. Flush on exit.
    def _flush():
        try:
            _log_file_handle.flush()
            _log_file_handle.write(
                f"\n Session end: {datetime.datetime.now().isoformat()}\n"
            )
            _log_file_handle.flush()
        except Exception:
            pass

    atexit.register(_flush)

    logging.getLogger("ios_logging").info(
        "On-device logging installed at %s", _log_path
    )
    return _log_path
