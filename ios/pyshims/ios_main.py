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

import sys
import traceback


class _IOSKeepRunning(BaseException):
    pass


def main() -> None:
    sys.argv = ["rayforge"]

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw

    def _ios_run(self, argv=None):
        # Equivalent of g_application_run() minus the blocking loop:
        # ::startup (adw_init etc.) fires during register, ::activate
        # builds the window. The CADisplayLink pump dispatches from
        # here on.
        self.register(None)
        self.activate()
        raise _IOSKeepRunning()

    Adw.Application.run = _ios_run

    try:
        import rayforge.app

        rayforge.app.main()
        # main() returning means run() was never reached (e.g. argparse
        # exit) — that is a failure for our purposes.
        print("RAYFORGE BOOT FAILED: main() returned without starting UI")
    except _IOSKeepRunning:
        print("RAYFORGE UI RUNNING")
    except SystemExit as e:
        print(f"RAYFORGE BOOT FAILED: SystemExit({e.code})")
        traceback.print_exc()
    except BaseException:
        print("RAYFORGE BOOT FAILED")
        traceback.print_exc()


if __name__ == "__main__":
    main()
