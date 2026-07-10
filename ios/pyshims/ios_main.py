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

    # iOS sandbox: only Documents/, Library/ and tmp/ inside the data
    # container are writable — platformdirs' default ~/.local/state is
    # not (PermissionError on device; the simulator was permissive).
    # Config goes to Documents so machine configs are visible in the
    # Files app; state/data/cache go to Library.
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
        _ioslog(f"SSL CA bundle: {certifi.where()}")
    except Exception as _e:
        _ioslog(f"certifi unavailable: {_e!r}")

    # The C shell sets HOME to the container's Documents directory (so
    # GTK file choosers and g_get_home_dir land somewhere user-visible).
    # The sandbox container root is its parent; Library sits next to
    # Documents there.
    _home = os.environ.get("HOME", "")
    if _home:
        _docs = _home if os.path.basename(_home) == "Documents"             else os.path.join(_home, "Documents")
        _lib = os.path.join(os.path.dirname(_docs), "Library")
        _xdg = {
            "XDG_CONFIG_HOME": os.path.join(_docs, "config"),
            "XDG_STATE_HOME": os.path.join(_lib, "state"),
            "XDG_DATA_HOME": os.path.join(_lib, "data"),
            "XDG_CACHE_HOME": os.path.join(_lib, "caches"),
        }
        for _k, _v in _xdg.items():
            os.environ.setdefault(_k, _v)
            try:
                os.makedirs(os.environ[_k], exist_ok=True)
            except OSError as _e:
                _ioslog(f"XDG dir {_k}={_v} not creatable: {_e}")
    try:
        if _home and os.path.isdir(_home):
            os.chdir(_home)
            _ioslog(f"cwd: {_home}")
    except OSError as _e:
        _ioslog(f"chdir failed: {_e!r}")
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

    # Diagnostic: a 100ms GLib timer that logs every 5s with the real
    # elapsed wall time. If the logged interval >> 5s while the app is
    # untouched, GLib timeout dispatch is starving without input —
    # pinpointing the "stuck until I pan" report at the main-loop level.
    def _ios_heartbeat_start():
        import time as _t
        from gi.repository import GLib as _GLib
        state = {"n": 0, "t": _t.monotonic()}

        def _beat():
            state["n"] += 1
            if state["n"] % 50 == 0:
                now = _t.monotonic()
                _ioslog(
                    "heartbeat: 50 ticks (5.0s nominal) took "
                    f"{now - state['t']:.2f}s"
                )
                state["t"] = now
            return True

        _GLib.timeout_add(100, _beat)

    _ios_heartbeat_start()

    # Fire-watch preview: a small live camera box (bottom-right) fed
    # by 1 fps snapshots from the CAM node. Fully defensive: any
    # failure logs once and the app runs without the box.
    def _ios_camera_box_start(app):
        import threading
        import urllib.request
        from gi.repository import Gtk, GLib, Gdk, GdkPixbuf

        state = {"pic": None, "fails": 0}

        def _fetch():
            try:
                with urllib.request.urlopen(
                    "http://rayforge-cam.local/jpg", timeout=3
                ) as r:
                    return r.read()
            except Exception:
                return None

        def _apply(data):
            try:
                loader = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
                loader.write(data)
                loader.close()
                pb = loader.get_pixbuf()
                pic = state["pic"]
                if pb is not None and pic is not None:
                    # Gtk.Picture renders at the paintable's NATURAL size
                    # (set_size_request is only a minimum), so scale the
                    # frame itself: factor 0.25.
                    pb = pb.scale_simple(
                        max(1, pb.get_width() // 4),
                        max(1, pb.get_height() // 4),
                        GdkPixbuf.InterpType.BILINEAR,
                    )
                    pic.set_paintable(
                        Gdk.Texture.new_for_pixbuf(pb)
                    )
                    pic.set_visible(True)
            except Exception:
                pass
            return False

        def _hide():
            try:
                if state["pic"] is not None:
                    state["pic"].set_visible(False)
            except Exception:
                pass
            return False

        def _tick():
            def worker():
                data = _fetch()
                if data:
                    state["fails"] = 0
                    GLib.idle_add(_apply, data)
                else:
                    state["fails"] += 1
                    if state["fails"] == 5:
                        GLib.idle_add(_hide)
            threading.Thread(target=worker, daemon=True).start()
            return True

        def _install():
            # Adw-safe: never re-parent window content. MainWindow already
            # owns a Gtk.Overlay around the canvas (_canvas_overlay); we
            # only add_overlay() a Picture onto it. Retries until the
            # window + overlay exist, gives up after ~30 s.
            state["tries"] = state.get("tries", 0) + 1
            try:
                win = app.get_active_window()
                overlay = getattr(win, "_canvas_overlay", None)
                if overlay is None or not isinstance(overlay, Gtk.Overlay):
                    if state["tries"] > 30:
                        _ioslog("camera box: no _canvas_overlay; giving up")
                        return False
                    return True  # retry
                pic = Gtk.Picture()
                pic.set_size_request(1, 1)  # size comes from the scaled frame
                pic.set_halign(Gtk.Align.END)
                pic.set_valign(Gtk.Align.END)
                pic.set_margin_end(12)
                pic.set_margin_bottom(12)
                pic.set_can_target(False)  # clicks pass through to canvas
                pic.add_css_class("card")
                pic.set_visible(False)  # shown on first good frame
                overlay.add_overlay(pic)
                state["pic"] = pic
                GLib.timeout_add(400, _tick)
                _ioslog("camera box installed (canvas overlay)")
            except Exception as e:
                _ioslog(f"camera box failed: {e}")
            return False

        GLib.timeout_add(4000, _install)

    def _ios_run(self, argv=None):
        # Equivalent of g_application_run() minus the blocking loop:
        # ::startup (adw_init etc.) fires during register, ::activate
        # builds the window. The CADisplayLink pump dispatches from
        # here on.
        _ioslog("_ios_run: register()")
        self.register(None)
        # Keep the GApplication alive forever: on iOS the app lifecycle
        # belongs to UIKit, never to "last window closed" (closing the
        # consent dialog must not quit the app).
        self.hold()
        _ioslog("_ios_run: hold() — app pinned alive")
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

        from gi.repository import GLib, Gtk, Gdk

        def _geom_probe():
            # Runs after the pump starts and widgets are allocated, so we
            # can compare GTK's allocation to the surface we forced.
            try:
                disp = Gdk.Display.get_default()
                mons = disp.get_monitors()
                for i in range(mons.get_n_items()):
                    m = mons.get_item(i)
                    g = m.get_geometry()
                    _ioslog("GEOM monitor[%d] %dx%d+%d+%d scale=%d" % (
                        i, g.width, g.height, g.x, g.y,
                        m.get_scale_factor()))
                tops = Gtk.Window.get_toplevels()
                for i in range(tops.get_n_items()):
                    w = tops.get_item(i)
                    surf = w.get_surface()
                    sw = surf.get_width() if surf is not None else -1
                    sh = surf.get_height() if surf is not None else -1
                    ss = surf.get_scale_factor() if surf is not None else -1
                    _ioslog("GEOM top[%d] %r alloc=%dx%d surface=%dx%d "
                            "surfscale=%d vis=%s" % (
                                i, w.get_title() or "?",
                                w.get_width(), w.get_height(),
                                sw, sh, ss, w.get_visible()))
            except Exception as e:
                _ioslog("GEOM probe failed: %r" % (e,))
            return False

        GLib.timeout_add_seconds(4, _geom_probe)
        _ios_camera_box_start(self)  # Adw-safe: overlays onto _canvas_overlay
        raise _IOSKeepRunning()

    Adw.Application.run = _ios_run

    try:
        _ioslog("import rayforge.app")
        import rayforge.app

        # iOS has no worker subprocess to build the addon manifest, so
        # rayforge's lazy addon finder sleeps 0.5s on every rayforge_addons
        # import (~160 of them => ~80s) before giving up. Those imports fail
        # on iOS either way; make the finder give up immediately so boot
        # doesn't blow past iOS's ~20s launch-responsiveness watchdog.
        try:
            from rayforge.addon_mgr.lazy_loader import AddonModuleFinder

            AddonModuleFinder.find_spec = (
                lambda self, fullname, path, target=None: None
            )
            _ioslog("addon finder fast-fail installed")
        except Exception as e:
            _ioslog("addon finder patch failed: %r" % (e,))

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
