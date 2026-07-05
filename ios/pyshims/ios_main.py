"""iOS entry shim for Rayforge.

Runs rayforge.app.main() unmodified, with one surgical intervention:
Adw.Application.run() is replaced by register() + activate() + a
controlled non-Exception unwind. Rationale:

  * The blocking GLib main loop inside run() would stall the UIKit run
    loop — on iOS the GDK backend's CADisplayLink pump IS the main
    loop (see gdk_ios_application_run in the GDK iOS backend).
  * main() continues into a full shutdown sequence as soon as run()
    returns with a window present, which would tear the app down
    immediately. _IOSKeepRunning derives from BaseException (not
    Exception), so no `except Exception` inside main() can swallow it;
    we unwind main() right after the UI is up and leave everything
    running under the UIKit loop.

Printed markers (captured by CI):
  RAYFORGE UI RUNNING   — main() completed startup, window presented
  RAYFORGE BOOT FAILED  — traceback follows
"""

import os
import sys
import traceback


def _ioslog(msg: str) -> None:
    # fd 2 is what the simulator actually captures (g_message lands there);
    # Python's own print()/stderr were being dropped.
    try:
        os.write(2, ("IOSBOOT: " + msg + "\n").encode("utf-8", "replace"))
    except Exception:
        pass


class _FdWriter:
    """Forward Python stdout/stderr straight to fd 2 so nothing is lost."""

    def write(self, s):
        try:
            if isinstance(s, str):
                s = s.encode("utf-8", "replace")
            os.write(2, s)
        except Exception:
            pass
        return len(s) if s is not None else 0

    def flush(self):
        pass


def _install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        _ioslog("UNCAUGHT " + "".join(
            traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = hook


class _IOSKeepRunning(BaseException):
    pass


def main() -> None:
    sys.stdout = _FdWriter()
    sys.stderr = _FdWriter()
    _install_excepthook()
    _ioslog("ios_main.main() start")
    # No desktop OpenGL on iOS: keep Rayforge's 3D canvas on its
    # placeholder so the GL widget is never instantiated. (The OpenGL
    # *imports* are additionally satisfied by the pyshims OpenGL stub;
    # this flag ensures none of that inert GL code is ever executed.)
    os.environ.setdefault("RAYFORGE_DISABLE_3D", "1")
    sys.argv = ["rayforge"]

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw

    # iOS-CPython ships no _posixshmem; in the single-process thread
    # model shared memory is an in-process registry. Install the shim
    # BEFORE any rayforge import (pipeline.artifact.store imports
    # multiprocessing.shared_memory at module level).
    import multiprocessing

    import rayforge_ios_shm

    sys.modules["multiprocessing.shared_memory"] = rayforge_ios_shm
    multiprocessing.shared_memory = rayforge_ios_shm

    # pyserial's list_ports platform dispatch does not know iOS and
    # raises ImportError at module import time. Serial hardware is
    # unavailable on iOS anyway (no USB serial without MFi), so an
    # empty-port implementation is the correct behavior, not a stub.
    import types

    _lp = types.ModuleType("serial.tools.list_ports")
    _lp.comports = lambda *a, **kw: []
    _lp.grep = lambda *a, **kw: iter(())
    _lp.main = lambda *a, **kw: None
    sys.modules["serial.tools.list_ports"] = _lp

    def _ios_run(self, argv=None):
        # Equivalent of g_application_run() minus the blocking loop:
        # ::startup (adw_init etc.) fires during register, ::activate
        # builds the window. The CADisplayLink pump dispatches from
        # here on.
        _ioslog("_ios_run: register()")
        self.register(None)
        _ioslog("_ios_run: activate()")
        self.activate()
        try:
            wins = self.get_windows()
            _ioslog("_ios_run: activate() returned; windows=%d" % len(wins))
            for w in wins:
                _ioslog("  window mapped=%s visible=%s title=%r" % (
                    w.get_mapped(), w.get_visible(), w.get_title()))
        except Exception as e:
            _ioslog("_ios_run: window introspection failed: %r" % (e,))
        raise _IOSKeepRunning()

    Adw.Application.run = _ios_run

    try:
        _ioslog("import rayforge.app")
        import rayforge.app

        _ioslog("rayforge.app.main()")
        rayforge.app.main()
        # main() returning means run() was never reached (e.g. argparse
        # exit) — that is a failure for our purposes.
        _ioslog("rayforge.app.main() returned without starting UI")
        print("RAYFORGE BOOT FAILED: main() returned without starting UI")
    except _IOSKeepRunning:
        _ioslog("keep-running caught — startup unwound cleanly")
        print("RAYFORGE UI RUNNING")
    except SystemExit as e:
        _ioslog("SystemExit(%r)" % (e.code,))
        print(f"RAYFORGE BOOT FAILED: SystemExit({e.code})")
        traceback.print_exc()
    except BaseException as e:
        _ioslog("BOOT EXC %s: %s" % (type(e).__name__, e))
        print("RAYFORGE BOOT FAILED")
        traceback.print_exc()


if __name__ == "__main__":
    main()
