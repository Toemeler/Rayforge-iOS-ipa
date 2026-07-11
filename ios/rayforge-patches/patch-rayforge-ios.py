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
        "                        elif (\n"
        "                            _m.driver_name == 'GrblTelnetDriver'\n"
        "                            and (_m.driver_args or {}).get(\n"
        "                                'host') == 'rayforge-laser.local'\n"
        "                            and (_m.driver_args or {}).get(\n"
        "                                'poll_status_while_running')\n"
        "                            is False\n"
        "                            and (_m.driver_args or {}).get(\n"
        "                                'deadlock_detection') is False\n"
        "                        ):\n"
        "                            # v4: our exact earlier defaults ->\n"
        "                            # live position polling during\n"
        "                            # jobs. Any user-edited arg stops\n"
        "                            # this from re-applying.\n"
        "                            _m.driver_args = dict(\n"
        "                                _m.driver_args,\n"
        "                                poll_status_while_running=True,\n"
        "                            )\n"
        "                            self._machine_mgr.save_machine(_m)\n"
        "                            logger.info(\n"
        "                                'iOS: job status polling on'\n"
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
        "                                'http://rayforge-cam.local'\n"
        "                                ':81/stream',\n"
        "                            )\n"
        "                            _c.enabled = True\n"
        "                            _m.add_camera(_c)\n"
        "                            self._machine_mgr.save_machine(_m)\n"
        "                            logger.info(\n"
        "                                'iOS: attached laser camera'\n"
        "                            )\n"
        "                        for _c in list(_m.cameras):\n"
        "                            if _c.device_id == (\n"
        "                                'http://rayforge-laser'\n"
        "                                '.local:81/stream'\n"
        "                            ):\n"
        "                                # v5: camera moved to its\n"
        "                                # own mDNS name (no-wires\n"
        "                                # topology).\n"
        "                                _c.device_id = (\n"
        "                                    'http://rayforge-cam'\n"
        "                                    '.local:81/stream'\n"
        "                                )\n"
        "                                self._machine_mgr\\\n"
        "                                    .save_machine(_m)\n"
        "                                logger.info(\n"
        "                                    'iOS: camera -> cam node'\n"
        "                                )\n"
        "                            if _c.name == 'Laser Camera':\n"
        "                                # v6: side-mounted monitoring\n"
        "                                # cam: canvas overlay off by\n"
        "                                # default. Rename marks the\n"
        "                                # migration done, so a user\n"
        "                                # re-enable in settings sticks.\n"
        "                                _c.name = 'Fire Watch'\n"
        "                                _c.enabled = False\n"
        "                                self._machine_mgr\\\n"
        "                                    .save_machine(_m)\n"
        "                                logger.info(\n"
        "                                    'iOS: camera overlay off'\n"
        "                                )\n"
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
    # P17: no update checks. A sideloaded ipa has no self-update path,
    # so the startup addon/app-version checks are pointless network
    # chatter (and a spinner) on every launch.
    (
        "rayforge/ui_gtk/mainwindow.py",
        "        # Trigger the non-blocking check for addon updates\n"
        "        self.update_cmd.check_for_updates_on_startup()\n"
        "\n"
        "        # Trigger the non-blocking check for app version updates\n"
        "        self.app_update_checker.check_on_startup()",
        "        # iOS: update checks removed — a sideloaded ipa cannot\n"
        "        # self-update; checking is noise on every launch.\n"
        "        pass",
    ),
    # P18: auto-home once per app launch on the FIRST successful
    # connect (not on reconnects, so a WiFi blip mid-positioning can
    # never surprise-home the head). GRBL with homing enabled boots in
    # alarm and rejects motion until homed — this also removes the
    # stuck/slow first job.
    (
        "rayforge/machine/driver/grbl/grbl_serial.py",
        '                logger.info("Connection established successfully.")',
        '                logger.info("Connection established successfully.")\n'
        "                if not getattr(\n"
        "                    type(self), '_ios_autohomed', False\n"
        "                ):\n"
        "                    setattr(type(self), '_ios_autohomed', True)\n"
        "\n"
        "                    async def _ios_home(drv=self):\n"
        "                        try:\n"
        "                            await asyncio.sleep(2.0)\n"
        "                            await drv.home()\n"
        "                            logger.info('iOS: auto-home done')\n"
        "                        except Exception:\n"
        "                            logger.exception(\n"
        "                                'iOS: auto-home failed'\n"
        "                            )\n"
        "\n"
        "                    asyncio.create_task(_ios_home())",
    ),
    # P19 (v2): respect $INSUNITS (upstream behavior), but LOG the
    # conversion. The old P19 forced mm and broke genuinely inch-
    # authored files (e.g. planetary.dxf: $INSUNITS=1, 1.1953 in
    # geometry = 30.36 mm; forcing mm shrank it to 1.2 mm). The
    # original "25.4x too big" symptom was the pyvips render failure,
    # not a units bug — verified against unpatched upstream, which
    # imports planetary.dxf at exactly 30.36 mm.
    (
        "rayforge/image/dxf/importer.py",
        '    def _get_scale_to_mm(self, doc, default: float = 1.0) -> float:\n'
        '        insunits = doc.header.get("$INSUNITS", 0)\n'
        "        return units_to_mm.get(insunits, default) or default",
        '    def _get_scale_to_mm(self, doc, default: float = 1.0) -> float:\n'
        '        insunits = doc.header.get("$INSUNITS", 0)\n'
        "        scale = units_to_mm.get(insunits, default) or default\n"
        "        import logging as _lg\n"
        "        _lg.getLogger(__name__).info(\n"
        '            "DXF $INSUNITS=%s -> scale_to_mm=%s", insunits, scale,\n'
        "        )\n"
        "        return scale",
    ),
    # P22: upstream hardcodes thumbnail line_width=2.0 in GEOMETRY
    # units; for small-native-unit files (inch DXF, ~1.2 units) the
    # stroke floods the whole canvas -> solid gray thumbnail. Passing
    # None uses the renderer's scale-aware default (~1 px).
    (
        "rayforge/image/dxf/importer.py",
        "        return render_geometry_to_png(\n"
        "            merged,\n"
        "            size,\n"
        "            line_width=2.0,\n"
        "            color=(0.2, 0.2, 0.2, 1.0),\n"
        "        )",
        "        return render_geometry_to_png(\n"
        "            merged,\n"
        "            size,\n"
        "            line_width=None,\n"
        "            color=(0.2, 0.2, 0.2, 1.0),\n"
        "        )",
    ),
    # P23: geo_renderer's default stroke width has a 0.5 GEOMETRY-unit
    # floor; for small-unit files (inch DXF) that's ~100 px and floods
    # the thumbnail. Use a fixed 1.5 px width in geometry units.
    (
        "rayforge/image/geo_renderer.py",
        "    width = line_width if line_width is not None else "
        "max(1.0 / scale, 0.5)",
        "    width = line_width if line_width is not None else "
        "1.5 / scale",
    ),
    # P24: promote the fit-check inputs to INFO so the on-device
    # session log shows WHY an import was called oversized (bbox vs
    # work_area), including per-item natural sizes.
    (
        "rayforge/doceditor/file_cmd.py",
        "        bbox_x, bbox_y, bbox_w, bbox_h = bbox\n"
        "        area_x, area_y, area_w, area_h = config.machine.work_area\n"
        "        logger.debug(",
        "        bbox_x, bbox_y, bbox_w, bbox_h = bbox\n"
        "        area_x, area_y, area_w, area_h = config.machine.work_area\n"
        "        logger.info(\n"
        "            'fit-check: bbox=(%.3f, %.3f, %.3f, %.3f) '\n"
        "            'work_area=(%.3f, %.3f, %.3f, %.3f) items=%s',\n"
        "            bbox_x, bbox_y, bbox_w, bbox_h,\n"
        "            area_x, area_y, area_w, area_h,\n"
        "            [\n"
        "                (type(i).__name__,\n"
        "                 getattr(i, 'natural_width_mm', None),\n"
        "                 getattr(i, 'natural_height_mm', None))\n"
        "                for i in content_items\n"
        "            ],\n"
        "        )\n"
        "        logger.debug(",
    ),
    # P25: log which importer class handles a file — the device log
    # showed a DXF import with ZERO DxfImporter log output, so verify
    # the registry actually picked DxfImporter.
    (
        "rayforge/doceditor/file_cmd.py",
        "            importer = importer_cls(\n"
        "                data=file_bytes, source_file=Path(filename)\n"
        "            )\n"
        "            import_result = importer.get_doc_items(spec)",
        "            logger.info(\n"
        "                'import preview: %s handles %s (spec=%s)',\n"
        "                importer_cls.__name__, filename,\n"
        "                type(spec).__name__,\n"
        "            )\n"
        "            importer = importer_cls(\n"
        "                data=file_bytes, source_file=Path(filename)\n"
        "            )\n"
        "            import_result = importer.get_doc_items(spec)",
    ),
    # P26: iOS reports unknown file types as application/octet-stream;
    # RuidaImporter registers that generic mime, so a .dxf opened via
    # the file dialog was parsed as a binary Ruida job -> garbage
    # geometry (device log: 95x1576 mm from a 30 mm file). Treat
    # generic mimes as untrusted and let the extension decide; log the
    # final choice.
    (
        "rayforge/doceditor/file_cmd.py",
        "        importer_cls = None\n"
        "        if mime_type:\n"
        "            importer_cls = importer_registry.get_by_mime_type("
        "mime_type)\n"
        "\n"
        "        if not importer_cls and file_path.suffix:\n"
        "            importer_cls = importer_registry.get_by_extension(\n"
        "                file_path.suffix.lower()\n"
        "            )\n"
        "\n"
        "        if importer_cls:\n"
        "            return importer_cls, importer_cls.features\n"
        "        return None, set()",
        "        _GENERIC_MIMES = {\n"
        "            'application/octet-stream',\n"
        "            'text/plain',\n"
        "            'application/x-unknown',\n"
        "        }\n"
        "        importer_cls = None\n"
        "        if mime_type and mime_type not in _GENERIC_MIMES:\n"
        "            importer_cls = importer_registry.get_by_mime_type("
        "mime_type)\n"
        "\n"
        "        if not importer_cls and file_path.suffix:\n"
        "            importer_cls = importer_registry.get_by_extension(\n"
        "                file_path.suffix.lower()\n"
        "            )\n"
        "\n"
        "        if not importer_cls and mime_type in _GENERIC_MIMES:\n"
        "            # No extension match: fall back to the generic mime.\n"
        "            importer_cls = importer_registry.get_by_mime_type("
        "mime_type)\n"
        "\n"
        "        logger.info(\n"
        "            'importer selection: file=%s mime=%s -> %s',\n"
        "            file_path.name, mime_type,\n"
        "            importer_cls.__name__ if importer_cls else None,\n"
        "        )\n"
        "        if importer_cls:\n"
        "            return importer_cls, importer_cls.features\n"
        "        return None, set()",
    ),
    # P21: log the imported DXF's computed world size (mm) so a wrong
    # on-device size is diagnosable from the session log.
    (
        "rayforge/image/dxf/importer.py",
        "        # 6. Final Result\n"
        "        result = ParsingResult(",
        "        # 6. Final Result\n"
        "        import logging as _lg\n"
        "        _lg.getLogger(__name__).info(\n"
        "            'DXF import: world_frame=%s scale=%s',\n"
        "            world_frame, native_unit_to_mm,\n"
        "        )\n"
        "        result = ParsingResult(",
    ),
    # P20: 10 Hz idle status polling (was 2 Hz). Two purposes: live
    # position feel, and — critical on the BT relay — steady traffic
    # keeps the DevKit's WiFi/BT radios out of deep power-save, so a
    # jog never pays the radio wake-up tax (100-300 ms otherwise).
    (
        "rayforge/machine/driver/grbl/grbl_serial.py",
        "                    await asyncio.sleep(0.5)\n"
        "\n"
        "                    if not self.keep_running or not "
        "transport.is_connected:",
        "                    await asyncio.sleep(0.1)  # iOS: keep-warm\n"
        "\n"
        "                    if not self.keep_running or not "
        "transport.is_connected:",
    ),
]


# (rel, old, new, expected_count): applied to ALL occurrences, with the
# count asserted so upstream drift is caught loudly.
REPLACE_ALL = [
    # Command timeout 10s -> 120s: GRBL does not ack '$H' until homing
    # finishes; 600mm homing takes >10s, so the driver aborted mid-home
    # and desynced the queue (seen in the on-device session log).
    (
        "rayforge/machine/driver/grbl/grbl_serial.py",
        "await asyncio.wait_for(request.finished.wait(), timeout=10.0)",
        "await asyncio.wait_for(request.finished.wait(), timeout=120.0)",
        2,
    ),
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
