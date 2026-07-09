#!/usr/bin/env python3
"""Patch a Rayforge source tree for iOS.

iOS forbids fork() and cannot spawn a second Python interpreter, so
multiprocessing is unavailable. Three anchor-verified patches route the
task system to the in-process ThreadPoolManager (rayforge_ios_pool.py,
protocol-identical to WorkerPoolManager, verified against Rayforge's
own ExecutionContextProxy/_TaggedQueue) on sys.platform == 'ios' and
keep desktop behavior untouched everywhere else:

  P1 shared/tasker/manager.py   import switch: ThreadPoolManager on iOS
  P2 shared/tasker/manager.py   plain dict instead of SyncManager dict
  P3 shared/tasker/manager.py   guard the SyncManager shutdown

Usage: patch-rayforge-ios.py <rayforge-source-dir>
Idempotent; exits non-zero with a message if any anchor is missing so
an upstream refactor is caught at patch time.
"""

import sys
from pathlib import Path

PATCHES = [
    (
        "rayforge/shared/tasker/manager.py",
        "from .pool import WorkerPoolManager",
        "import sys as _sys\n"
        "if _sys.platform == 'ios':\n"
        "    # iOS: no fork/spawn — protocol-identical thread pool\n"
        "    from rayforge_ios_pool import ThreadPoolManager as WorkerPoolManager\n"
        "else:\n"
        "    from .pool import WorkerPoolManager",
    ),
    (
        "rayforge/shared/tasker/manager.py",
        '        self._manager = get_context("spawn").Manager()\n'
        "        if shared_state is None:\n"
        "            shared_state = self._manager.dict()",
        "        if _sys.platform == 'ios':\n"
        "            # in-process: a plain dict fulfills the DictProxy role\n"
        "            self._manager = None\n"
        "            if shared_state is None:\n"
        "                shared_state = {}\n"
        "        else:\n"
        '            self._manager = get_context("spawn").Manager()\n'
        "            if shared_state is None:\n"
        "                shared_state = self._manager.dict()",
    ),
    (
        "rayforge/shared/tasker/manager.py",
        "            self._manager.shutdown()",
        "            if self._manager is not None:\n"
        "                self._manager.shutdown()",
    ),
    # P4/P5: half zoom sensitivity on iOS. on_scroll uses only the sign of
    # dy — one fixed step per scroll event — so trackpad gestures (many
    # events per swipe) zoom far too fast at 10%. 5% per step = half.
    (
        "rayforge/ui_gtk/canvas/worldsurface.py",
        "        zoom_speed = 0.1",
        # iOS: two-finger scroll pans (both axes); zoom happens only via
        # pinch, whose synthesized scroll events the backend tags with
        # CONTROL. Zoom is proportional to the tagged magnitude.
        "        import math\n"
        "        from gi.repository import Gdk as _Gdk\n"
        "        _state = controller.get_current_event_state()\n"
        "        if not (_state & _Gdk.ModifierType.CONTROL_MASK):\n"
        "            _base = self._axis_renderer.get_base_pixels_per_mm(\n"
        "                self.get_width(), self.get_height()\n"
        "            )\n"
        "            _ppm = _base * self.zoom_level\n"
        "            if _ppm > 0:\n"
        "                self.set_pan(\n"
        "                    self.pan_x_mm + dx / _ppm,\n"
        "                    self.pan_y_mm - dy / _ppm,\n"
        "                )\n"
        "            return\n"
        "        zoom_speed = math.expm1(min(abs(dy), 120.0) * 0.002)",
    ),
    (
        "rayforge/builtin_addons/rayforge-addon-print-and-cut/"
        "print_and_cut/pick_surface.py",
        "        zoom_speed = 0.1",
        # iOS: zoom proportionally to the scroll magnitude instead of a
        # fixed 10% per event. Trackpads fire dozens of events per swipe
        # (each was a full step -> way too fast); the backend's pinch
        # sends dy = -ln(scale)/0.002 so a 2x pinch is a 2x zoom.
        "        import math\n"
        "        zoom_speed = math.expm1(min(abs(dy), 120.0) * 0.002)",
    ),
    # P6: the Cairo software renderer saturates the main loop during
    # zoom/pan; PRIORITY_DEFAULT_IDLE callbacks (task events, shm
    # adoption ACKs) starve past the 5s deadline, artifacts NACK, and
    # laser-op lines vanish until a later re-render. Dispatch worker->
    # main-thread callbacks at PRIORITY_DEFAULT instead.
    (
        "rayforge/shared/util/glib.py",
        "    GLib.idle_add(lambda: falsify(func, *args, **kwargs))",
        "    import sys as _sys\n"
        "    if _sys.platform == 'ios':\n"
        "        GLib.idle_add(lambda: falsify(func, *args, **kwargs),\n"
        "                      priority=GLib.PRIORITY_DEFAULT)\n"
        "    else:\n"
        "        GLib.idle_add(lambda: falsify(func, *args, **kwargs))",
    ),
    # P10: dx never reached on_scroll - the controller was created
    # VERTICAL-only, so GTK dropped horizontal deltas and sideways
    # two-finger panning did nothing.
    (
        "rayforge/ui_gtk/canvas/worldsurface.py",
        "        self._scroll_controller = Gtk.EventControllerScroll.new(\n"
        "            Gtk.EventControllerScrollFlags.VERTICAL\n"
        "        )",
        "        self._scroll_controller = Gtk.EventControllerScroll.new(\n"
        "            Gtk.EventControllerScrollFlags.BOTH_AXES\n"
        "        )",
    ),
    # P11: keep the stale ops surface when a re-render STARTS. Upstream
    # drops it immediately (fine on PC where the replacement lands in
    # ms); on iOS the replacement is slow or lost, which is exactly the
    # 'lines invisible until layer toggle' symptom.
    (
        "rayforge/ui_gtk/canvas2d/elements/workpiece.py",
        "        if workpiece_uid != self.data.uid or not self.canvas:\n"
        "            return\n"
        "        self._remove_ops_surface(step_uid)\n"
        "        self._composited_dirty = True\n"
        "        self.canvas.queue_draw()",
        "        if workpiece_uid != self.data.uid or not self.canvas:\n"
        "            return\n"
        "        import sys as _sys\n"
        "        if _sys.platform != 'ios':\n"
        "            self._remove_ops_surface(step_uid)\n"
        "        logger.warning(f'iOS-diag: artifact_created step={step_uid}')\n"
        "        self._composited_dirty = True\n"
        "        self.canvas.queue_draw()",
    ),
    # P12/P13: name the silent branch that eats the artifact.
    (
        "rayforge/ui_gtk/canvas2d/elements/workpiece.py",
        "        if view_handle is None:\n"
        "            return\n"
        "\n"
        "        artifact = self.view_manager.store.get(view_handle)\n"
        "        if not isinstance(artifact, WorkPieceViewArtifact):\n"
        "            return",
        "        if view_handle is None:\n"
        "            logger.warning(f'iOS-diag: no view handle step={step_uid}')\n"
        "            return\n"
        "\n"
        "        artifact = self.view_manager.store.get(view_handle)\n"
        "        if not isinstance(artifact, WorkPieceViewArtifact):\n"
        "            logger.warning(\n"
        "                f'iOS-diag: bad artifact step={step_uid}: '\n"
        "                f'{type(artifact).__name__}'\n"
        "            )\n"
        "            return",
    ),
    (
        "rayforge/ui_gtk/canvas2d/elements/workpiece.py",
        "        if workpiece_uid != self.data.uid:\n"
        "            return\n"
        "        edited = self.data._edited_boundaries",
        "        if workpiece_uid != self.data.uid:\n"
        "            return\n"
        "        logger.warning(f'iOS-diag: gen_finished step={step_uid}')\n"
        "        edited = self.data._edited_boundaries",
    ),
    # P8: a transiently blank view buffer (read race with the worker /
    # a NACKed handle) removed the cached ops surface -> laser lines
    # invisible until a full regeneration (e.g. layer visibility
    # toggle). Keep the previous surface instead; stale beats blank.
    (
        "rayforge/ui_gtk/canvas2d/elements/workpiece.py",
        "            if not np.any(new_data):\n"
        "                self._remove_ops_surface(step_uid)\n"
        "                self._invalidate_composited()\n"
        "                return",
        "            if not np.any(new_data):\n"
        "                import sys as _sys\n"
        "                if _sys.platform == 'ios':\n"
        "                    logger.warning(\n"
        "                        f'iOS-diag: blank buffer step={step_uid}'\n"
        "                    )\n"
        "                    return  # keep previous surface\n"
        "                self._remove_ops_surface(step_uid)\n"
        "                self._invalidate_composited()\n"
        "                return",
    ),
    # P9: NACK-on-timeout destroys the artifact the main thread is about
    # to adopt; under software-rendering load 5s is too tight. The wait
    # only parks a worker thread, so be generous.
    (
        "rayforge/shared/tasker/proxy.py",
        "        timeout: float = 5.0,",
        "        timeout: float = 30.0,",
    ),
    # P14: real SVG rendering on iOS. Neither libvips svgload (pyvips
    # is a Phase-2 stub) nor the Rsvg GIR exists in the bundle, so every
    # workpiece render raised 'Namespace Rsvg not available' and retried
    # forever: the eternal progress bar and half-rendered laser lines in
    # the device log. rayforge_ios_svg rasterizes via svgelements
    # (already bundled, pure Python) + pycairo.
    (
        "rayforge/image/svg/svg_fallback.py",
        '    import cairo\n'
        '    import gi\n'
        '\n'
        '    gi.require_version("Rsvg", "2.0")\n'
        '    from gi.repository import Rsvg',
        "    import cairo\n"
        "    import sys as _sys\n"
        "    if _sys.platform == 'ios':\n"
        "        try:\n"
        "            from rayforge_ios_svg import render_svg_to_cairo_ios\n"
        "            return render_svg_to_cairo_ios(svg_data, width, height)\n"
        "        except Exception:\n"
        "            logger.exception('iOS svgelements renderer failed')\n"
        "            return None\n"
        '    import gi\n'
        '\n'
        '    gi.require_version("Rsvg", "2.0")\n'
        '    from gi.repository import Rsvg',
    ),
    # P15: preconfigured machine. On first run (no machines), create
    # the Sculpfun S30 Ultra 11W from its bundled device profile instead
    # of a blank generic machine, so the app is ready to use out of the
    # box for this user's laser.
    (
        "rayforge/context.py",
        "            self._machine_mgr = MachineManager(MACHINE_DIR)\n"
        "            if not self._machine_mgr.machines:\n"
        "                self._machine_mgr.create_default_machine()",
        "            self._machine_mgr = MachineManager(MACHINE_DIR)\n"
        "            import sys as _sys\n"
        "            if not self._machine_mgr.machines:\n"
        "                _created = False\n"
        "                if _sys.platform == 'ios':\n"
        "                    try:\n"
        "                        from .config import BUILTIN_DEVICES_DIR\n"
        "                        from .machine.device.profile import (\n"
        "                            DeviceProfile,\n"
        "                        )\n"
        "                        _prof = DeviceProfile.from_path(\n"
        "                            BUILTIN_DEVICES_DIR\n"
        "                            / 'sculpfun-s30-ultra-11w'\n"
        "                        )\n"
        "                        _m = _prof.create_machine(self)\n"
        "                        self._machine_mgr.save_machine(_m)\n"
        "                        _created = True\n"
        "                        logger.info(\n"
        "                            'iOS: created Sculpfun S30 Ultra 11W'\n"
        "                        )\n"
        "                    except Exception:\n"
        "                        logger.exception(\n"
        "                            'iOS default machine setup failed'\n"
        "                        )\n"
        "                if not _created:\n"
        "                    self._machine_mgr.create_default_machine()\n"
        "            elif _sys.platform == 'ios':\n"
        "                # One-time migration: earlier iOS builds created\n"
        "                # the Sculpfun with GrblSerialDriver, which can\n"
        "                # never connect on iOS (no USB serial; the\n"
        "                # laser's Bluetooth is Classic SPP, blocked by\n"
        "                # Apple without MFi). Rewrite it to the telnet\n"
        "                # driver (WiFi, Grbl_ESP32 port 23). Drivers are\n"
        "                # not built yet here (initialize_connections\n"
        "                # runs later), so field mutation + save is\n"
        "                # inert and picked up on driver construction.\n"
        "                try:\n"
        "                    for _m in list(\n"
        "                        self._machine_mgr.machines.values()\n"
        "                    ):\n"
        "                        if (\n"
        "                            _m.driver_name == 'GrblSerialDriver'\n"
        "                            and 'sculpfun'\n"
        "                            in (_m.name or '').lower()\n"
        "                        ):\n"
        "                            _m.driver_name = 'GrblTelnetDriver'\n"
        "                            _m.driver_args = {\n"
        "                                'host': 'rayforge-laser.local',\n"
        "                                'port': 23,\n"
        "                                'poll_status_while_running':\n"
        "                                    False,\n"
        "                                'deadlock_detection': False,\n"
        "                            }\n"
        "                            self._machine_mgr.save_machine(_m)\n"
        "                            logger.info(\n"
        "                                'iOS: migrated %s to telnet',\n"
        "                                _m.name,\n"
        "                            )\n"
        "                        elif (\n"
        "                            _m.driver_name == 'GrblTelnetDriver'\n"
        "                            and (_m.driver_args or {}).get(\n"
        "                                'host') == '192.168.0.1'\n"
        "                        ):\n"
        "                            # v2: interim AP-mode sentinel ->\n"
        "                            # BT relay's mDNS name. A user-\n"
        "                            # edited host is left alone.\n"
        "                            _m.driver_args = dict(\n"
        "                                _m.driver_args,\n"
        "                                host='rayforge-laser.local',\n"
        "                            )\n"
        "                            self._machine_mgr.save_machine(_m)\n"
        "                            logger.info(\n"
        "                                'iOS: host -> relay mdns name'\n"
        "                            )\n"
        "                except Exception:\n"
        "                    logger.exception(\n"
        "                        'iOS telnet migration failed'\n"
        "                    )\n"
        "            if _sys.platform == 'ios':\n"
        "                # Auto-attach the laser camera (ESP32-CAM on\n"
        "                # the WiFi node) once, if the machine has no\n"
        "                # camera yet. Runs for fresh installs (right\n"
        "                # after profile creation above) and existing\n"
        "                # ones alike.\n"
        "                try:\n"
        "                    from .camera.models.camera import (\n"
        "                        Camera as _IosCam,\n"
        "                    )\n"
        "                    for _m in list(\n"
        "                        self._machine_mgr.machines.values()\n"
        "                    ):\n"
        "                        if (\n"
        "                            'sculpfun'\n"
        "                            in (_m.name or '').lower()\n"
        "                            and not _m.cameras\n"
        "                        ):\n"
        "                            _c = _IosCam(\n"
        "                                'Laser Camera',\n"
        "                                'http://rayforge-laser.local'\n"
        "                                ':81/stream',\n"
        "                            )\n"
        "                            _c.enabled = True\n"
        "                            _m.add_camera(_c)\n"
        "                            self._machine_mgr.save_machine(_m)\n"
        "                            logger.info(\n"
        "                                'iOS: attached laser camera'\n"
        "                            )\n"
        "                except Exception:\n"
        "                    logger.exception(\n"
        "                        'iOS camera attach failed'\n"
        "                    )",
    ),
    # P16: air assist ON by default. The S30 Ultra's pump is mainboard-
    # controlled (M8/M9) and the user wants it active for every
    # operation; upstream defaults each step's toggle to off. Job end
    # emits M9 (verified in the gcode encoder), so the pump stops.
    (
        "rayforge/core/step.py",
        "        self.air_assist: bool = False",
        "        self.air_assist: bool = True  # iOS: S30U auto air assist",
    ),
    # P7: icons. The iOS bundle has no gdk-pixbuf SVG loader (librsvg is
    # not built for iOS), so Gio.FileIcon/GdkPixbuf on Rayforge's .svg
    # icons render blank. The bundle step pre-rasterizes every icon SVG to
    # a PNG sibling (gdk-pixbuf's PNG loader is builtin); prefer it here.
    (
        "rayforge/ui_gtk/icons.py",
        '    filename = f"{icon_name}.svg"',
        "    import sys as _sys\n"
        "    if _sys.platform == 'ios':\n"
        "        # iOS: no SVG pixbuf loader — use the pre-rasterized PNG\n"
        '        _png = f"{icon_name}.png"\n'
        "        for search_path in _icon_search_paths:\n"
        "            candidate = search_path / _png\n"
        "            if candidate.is_file():\n"
        "                return candidate\n"
        "        try:\n"
        "            with importlib.resources.path(icons, _png) as path:\n"
        "                if path.is_file():\n"
        "                    return path\n"
        "        except Exception:\n"
        "            pass  # fall through to the .svg lookup\n"
        '    filename = f"{icon_name}.svg"',
    ),
]


# (rel, old, new, expected_count): applied to ALL occurrences, with the
# count asserted so upstream drift is caught loudly.
REPLACE_ALL = [
    # air assist default ON in every capability (Cut/Engrave/Raster)
    (
        "rayforge/core/capability.py",
        '''                BoolVar(
                    key="air_assist",
                    label=_("Air Assist"),
                    default=False,
                ),''',
        '''                BoolVar(
                    key="air_assist",
                    label=_("Air Assist"),
                    default=True,  # iOS: S30U auto air assist
                ),''',
        3,
    ),
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    if not (root / "rayforge").is_dir():
        print(f"error: {root} does not look like a rayforge tree")
        return 1

    for rel, old, new, count in REPLACE_ALL:
        path = root / rel
        text = path.read_text()
        if new in text:
            print(f"ok (already patched): {rel} [replace-all]")
            continue
        if text.count(old) != count:
            print(
                f"error: expected {count} occurrences in {rel}, "
                f"found {text.count(old)}"
            )
            return 1
        path.write_text(text.replace(old, new))
        print(f"patched: {rel} [{count}x] ({old.splitlines()[0][:40]}...)")

    for rel, old, new in PATCHES:
        path = root / rel
        text = path.read_text()
        if new in text:
            print(f"ok (already patched): {rel}")
            continue
        if old not in text:
            print(f"error: anchor not found in {rel}:\n---\n{old}\n---")
            return 1
        if text.count(old) != 1:
            print(f"error: anchor not unique in {rel}")
            return 1
        path.write_text(text.replace(old, new, 1))
        print(f"patched: {rel} ({old.splitlines()[0][:50]}...)")

    print("rayforge iOS patches applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
