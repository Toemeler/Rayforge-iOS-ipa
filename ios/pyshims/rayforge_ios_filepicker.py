"""Native iOS document picker as a Gtk.FileDialog drop-in.

Rayforge resolves `Gtk.FileDialog` at call time from the gi module
wrapper, so `install(Gtk)` swaps a single attribute and every dialog in
the app (import, open/save project, export g-code, machine profiles,
debug logs, camera calibration) becomes a native
UIDocumentPickerViewController — no anchored patches needed.

Implementation notes:
  * Pure ctypes against libobjc + UIKit; no C-backend changes.
  * OPEN: initForOpeningContentTypes:asCopy:YES — iOS copies the pick
    into the app sandbox, so no security-scoped access is needed.
  * SAVE: GTK's dialog picks a path BEFORE the app writes the file,
    but UIDocumentPicker exports an EXISTING file. Bridge: return a
    path in Documents/exports/ immediately (rayforge writes there),
    then present initForExportingURLs:asCopy:NO shortly after so the
    user places the file anywhere in Files. If they cancel, the file
    stays visible under On My iPad > Rayforge > exports.
  * API-compatible surface: new(), open(), save(), open_finish(),
    save_finish(); every unknown set_*/get_* is a no-op so future
    upstream setters cannot crash the shim.
  * Fully defensive: any ObjC failure falls back to the original
    Gtk.FileDialog.
"""

import ctypes
import ctypes.util
import logging
import os
import time

logger = logging.getLogger(__name__)

_objc = None
_send = None
_registered = {}
_alive = {}  # keep picker + delegate refs until dismissed


def _load_objc():
    global _objc
    if _objc is not None:
        return _objc
    _objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    # UIKit/Foundation are already loaded in the app process; libobjc
    # can see their classes without an explicit dlopen.
    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    _objc.sel_registerName.restype = ctypes.c_void_p
    _objc.sel_registerName.argtypes = [ctypes.c_char_p]
    _objc.objc_allocateClassPair.restype = ctypes.c_void_p
    _objc.objc_allocateClassPair.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t
    ]
    _objc.objc_registerClassPair.argtypes = [ctypes.c_void_p]
    _objc.class_addMethod.restype = ctypes.c_bool
    _objc.class_addMethod.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
    ]
    return _objc


def _sel(name):
    return _objc.sel_registerName(name.encode())


def _cls(name):
    return _objc.objc_getClass(name.encode())


def _msg(receiver, sel_name, *args, restype=ctypes.c_void_p,
         argtypes=None):
    """objc_msgSend with per-call casting (arm64-safe)."""
    if argtypes is None:
        argtypes = [ctypes.c_void_p] * len(args)
    fn = ctypes.cast(
        _objc.objc_msgSend,
        ctypes.CFUNCTYPE(
            restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes
        ),
    )
    return fn(receiver, _sel(sel_name), *args)


def _nsstring(py_str):
    return _msg(
        _cls("NSString"), "stringWithUTF8String:",
        py_str.encode("utf-8"), argtypes=[ctypes.c_char_p],
    )


def _nsstring_to_py(ns):
    if not ns:
        return None
    p = _msg(ns, "UTF8String", restype=ctypes.c_char_p)
    return p.decode("utf-8") if p else None


def _nsarray(objs):
    arr = (ctypes.c_void_p * len(objs))(*objs)
    return _msg(
        _cls("NSArray"), "arrayWithObjects:count:",
        arr, len(objs),
        argtypes=[ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong],
    )


def _root_view_controller():
    app = _msg(_cls("UIApplication"), "sharedApplication")
    win = _msg(app, "keyWindow")
    if not win:
        wins = _msg(app, "windows")
        n = _msg(wins, "count", restype=ctypes.c_ulong)
        if n:
            win = _msg(
                wins, "objectAtIndex:", 0, argtypes=[ctypes.c_ulong]
            )
    if not win:
        raise RuntimeError("no UIWindow available")
    vc = _msg(win, "rootViewController")
    if not vc:
        raise RuntimeError("no rootViewController")
    return vc


# --------------------------------------------------------------- delegate
_DELEGATE_IMPS = []  # prevent GC of CFUNCTYPE thunks
_pending = {}  # delegate ptr -> dict(on_pick, on_cancel)


def _make_delegate_class():
    if "cls" in _registered:
        return _registered["cls"]
    ObjCMethod = ctypes.CFUNCTYPE(
        None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p,
    )
    ObjCMethod1 = ctypes.CFUNCTYPE(
        None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    )

    def did_pick(self_ptr, _sel_ptr, _picker, urls):
        try:
            entry = _pending.pop(self_ptr, None)
            paths = []
            n = _msg(urls, "count", restype=ctypes.c_ulong)
            for i in range(n):
                url = _msg(
                    urls, "objectAtIndex:", i, argtypes=[ctypes.c_ulong]
                )
                path = _nsstring_to_py(_msg(url, "path"))
                if path:
                    paths.append(path)
            _alive.pop(self_ptr, None)
            if entry and entry.get("on_pick"):
                entry["on_pick"](paths)
        except Exception:
            logger.exception("iOS picker: did_pick failed")

    def was_cancelled(self_ptr, _sel_ptr, _picker):
        try:
            entry = _pending.pop(self_ptr, None)
            _alive.pop(self_ptr, None)
            if entry and entry.get("on_cancel"):
                entry["on_cancel"]()
        except Exception:
            logger.exception("iOS picker: cancel handler failed")

    imp_pick = ObjCMethod(did_pick)
    imp_cancel = ObjCMethod1(was_cancelled)
    _DELEGATE_IMPS.extend([imp_pick, imp_cancel])

    cls = _objc.objc_allocateClassPair(
        _cls("NSObject"), b"RFIOSPickerDelegate", 0
    )
    _objc.class_addMethod(
        cls,
        _sel("documentPicker:didPickDocumentsAtURLs:"),
        ctypes.cast(imp_pick, ctypes.c_void_p),
        b"v@:@@",
    )
    _objc.class_addMethod(
        cls,
        _sel("documentPickerWasCancelled:"),
        ctypes.cast(imp_cancel, ctypes.c_void_p),
        b"v@:@",
    )
    _objc.objc_registerClassPair(cls)
    _registered["cls"] = cls
    return cls


def _present_picker(picker, on_pick, on_cancel):
    cls = _make_delegate_class()
    delegate = _msg(_msg(cls, "alloc"), "init")
    _pending[delegate] = {"on_pick": on_pick, "on_cancel": on_cancel}
    _alive[delegate] = (picker, delegate)
    _msg(picker, "setDelegate:", delegate)
    vc = _root_view_controller()
    _msg(
        vc, "presentViewController:animated:completion:",
        picker, True, None,
        argtypes=[ctypes.c_void_p, ctypes.c_bool, ctypes.c_void_p],
    )


def present_open(on_pick, on_cancel):
    """Native open picker; picks are copied into the sandbox by iOS."""
    ut = _msg(
        _cls("UTType"), "typeWithIdentifier:", _nsstring("public.data")
    )
    types = _nsarray([ut])
    picker = _msg(
        _msg(_cls("UIDocumentPickerViewController"), "alloc"),
        "initForOpeningContentTypes:asCopy:",
        types, True,
        argtypes=[ctypes.c_void_p, ctypes.c_bool],
    )
    _present_picker(picker, on_pick, on_cancel)


def present_export(path, on_pick, on_cancel):
    """Native export sheet moving an existing file into Files."""
    url = _msg(
        _cls("NSURL"), "fileURLWithPath:", _nsstring(path)
    )
    picker = _msg(
        _msg(_cls("UIDocumentPickerViewController"), "alloc"),
        "initForExportingURLs:asCopy:",
        _nsarray([url]), False,
        argtypes=[ctypes.c_void_p, ctypes.c_bool],
    )
    _present_picker(picker, on_pick, on_cancel)


# ----------------------------------------------------------- Gtk bridge
def install(Gtk, Gio, GLib, documents_dir, ioslog=lambda m: None):
    """Replace Gtk.FileDialog with the native bridge (with fallback)."""
    try:
        _load_objc()
        _make_delegate_class()
    except Exception as e:
        ioslog(f"iOS file picker unavailable, keeping GTK dialog: {e!r}")
        return False

    RealFileDialog = Gtk.FileDialog
    export_dir = os.path.join(documents_dir, "exports")

    class IOSFileDialog:
        def __init__(self):
            self._initial_name = None
            self._picked = None  # Gio.File or None

        @staticmethod
        def new():
            return IOSFileDialog()

        # GTK setters rayforge uses today or may use tomorrow: accept
        # anything, honor what matters.
        def set_initial_name(self, name):
            self._initial_name = name

        def set_initial_file(self, gfile):
            try:
                self._initial_name = os.path.basename(gfile.get_path())
            except Exception:
                pass

        def __getattr__(self, name):
            if name.startswith(("set_", "get_")):
                return lambda *a, **kw: None
            raise AttributeError(name)

        # ------------------------------------------------------- open
        def open(self, win, cancellable, callback, user_data=None):
            def on_pick(paths):
                self._picked = (
                    Gio.File.new_for_path(paths[0]) if paths else None
                )
                GLib.idle_add(self._fire, callback, user_data)

            def on_cancel():
                self._picked = None
                GLib.idle_add(self._fire, callback, user_data)

            try:
                present_open(on_pick, on_cancel)
                ioslog("iOS file picker: open presented")
            except Exception:
                logger.exception("iOS open picker failed; GTK fallback")
                self._gtk_fallback("open", win, cancellable, callback,
                                   user_data)

        def open_finish(self, result):
            return self._picked

        # ------------------------------------------------------- save
        def save(self, win, cancellable, callback, user_data=None):
            """Ask for a name first, then write + present export sheet."""
            try:
                self._prompt_name(
                    win,
                    lambda name: self._do_save(name, callback, user_data),
                    lambda: self._cancel_save(callback, user_data),
                )
            except Exception:
                logger.exception("iOS save prompt failed; GTK fallback")
                self._gtk_fallback("save", win, cancellable, callback,
                                   user_data)

        def _prompt_name(self, win, on_ok, on_cancel):
            import gi
            gi.require_version("Adw", "1")
            from gi.repository import Adw

            name = self._initial_name or "untitled"
            base, ext = os.path.splitext(name)

            dlg = Adw.AlertDialog.new("Save As", None)
            entry = Gtk.Entry()
            entry.set_text(base)
            entry.set_activates_default(True)
            entry.set_margin_top(6)
            dlg.set_extra_child(entry)
            dlg.add_response("cancel", "Cancel")
            dlg.add_response("save", "Save")
            dlg.set_default_response("save")
            dlg.set_response_appearance(
                "save", Adw.ResponseAppearance.SUGGESTED
            )

            def on_response(_dlg, response):
                if response == "save":
                    text = entry.get_text().strip() or base
                    if ext and not text.endswith(ext):
                        text += ext
                    on_ok(text)
                else:
                    on_cancel()

            dlg.connect("response", on_response)
            parent = win if isinstance(win, Gtk.Widget) else None
            dlg.present(parent)
            entry.grab_focus()

        def _do_save(self, name, callback, user_data):
            try:
                os.makedirs(export_dir, exist_ok=True)
                base, ext = os.path.splitext(name)
                path = os.path.join(export_dir, name)
                i = 1
                while os.path.exists(path):
                    path = os.path.join(export_dir, f"{base}-{i}{ext}")
                    i += 1
                self._picked = Gio.File.new_for_path(path)
                GLib.idle_add(self._fire, callback, user_data)
                self._schedule_export(path)
                ioslog(f"iOS file picker: save -> {path}")
            except Exception:
                logger.exception("iOS save bridge failed")
                self._cancel_save(callback, user_data)

        def _cancel_save(self, callback, user_data):
            self._picked = None
            GLib.idle_add(self._fire, callback, user_data)

        def save_finish(self, result):
            return self._picked

        # --------------------------------------------------- plumbing
        def _fire(self, callback, user_data):
            try:
                try:
                    callback(self, None, user_data)
                except TypeError:
                    # some callbacks are (dialog, result) only
                    callback(self, None)
            except Exception:
                logger.exception("file dialog callback failed")
            return False

        def _schedule_export(self, path, attempts=0):
            """Present the export sheet once rayforge wrote the file."""
            def check():
                try:
                    if os.path.exists(path) and os.path.getsize(path) > 0:
                        mtime = os.path.getmtime(path)
                        if time.time() - mtime > 0.7:
                            present_export(
                                path,
                                lambda p: ioslog(
                                    f"exported to Files: {p}"
                                ),
                                lambda: ioslog(
                                    "export cancelled; file kept in "
                                    "Rayforge/exports"
                                ),
                            )
                            return False
                    if check.tries > 40:  # ~20 s: give up quietly
                        return False
                    check.tries += 1
                except Exception:
                    logger.exception("export sheet failed")
                    return False
                return True

            check.tries = 0
            GLib.timeout_add(500, check)

        def _gtk_fallback(self, mode, win, cancellable, callback,
                          user_data):
            real = RealFileDialog.new()
            if self._initial_name:
                try:
                    real.set_initial_name(self._initial_name)
                except Exception:
                    pass
            # route finish calls made on *self* to the real dialog
            self.open_finish = real.open_finish
            self.save_finish = real.save_finish
            if mode == "open":
                real.open(win, cancellable, callback, user_data)
            else:
                real.save(win, cancellable, callback, user_data)

    Gtk.FileDialog = IOSFileDialog
    ioslog("iOS file picker installed (Gtk.FileDialog replaced)")
    return True
