# Rayforge iOS — Handoff (2026-07-11, FINAL production build)

## State
All acute issues resolved and user-verified through this session:
DXF import (mime-routing P26 + INSUNITS respected), thumbnails
(pyvips PNG codec + P22/P23 stroke width), toolpath rendering
(P27 2x oversample + P28 stroke + send_event_and_wait in-process ack
+ NEW: live vector toolpaths), native iOS file pickers with save-name
prompt + filter honoring, camera fire-watch box (0.375 scale, 2.5 fps,
Adw-safe canvas-overlay attach), step menu (raygeo tag), 120 s GRBL
timeout, auto-home-once, telnet driver.

## Final build contents (commit after e70e362)
- **Vector toolpaths** (`rayforge_ios_vecops.py`): WorkPieceElement.draw
  wrapped at activate; ops from view_manager source artifacts drawn as
  live cairo strokes in element-local 1x1 space (normalize = mm /
  generation_size, matches raster convention). Crisp at every zoom,
  visible DURING gestures. Fallbacks -> upstream raster path: scanline
  steps (scanline_count property AND post-linearize scanline_map),
  >20k commands, missing handles, any exception (logged once).
  Validated end-to-end with planetary.dxf geometry (1458 cmds).
- **vtracer**: vendored pyo3-0.28 wrapper crate `ios/vtracer-rs`
  (PyPI binding pins pyo3 0.19 = no iOS target). API-identical
  convert_raw_image_to_svg. Conversion core = unmodified vtracer 0.6.
  Built in step12 [10d] via maturin aarch64-apple-ios next to raygeo;
  stub removed from staging. Core semantics validated locally via a
  Rust CLI harness driving rayforge's REAL tracing.py under shims.
- **cv2 shim additions**: COLOR_BGRA2GRAY, BORDER_CONSTANT,
  copyMakeBorder (constant), imencode('.bmp') with real-cv2 BGR
  semantics. **pyvips additions**: Image.black, invert (uint8+linear),
  used by the TraceSpec preview chain (thumbnail->flatten->invert).
- **raygeo v1.15.2** (upstream HEAD f36b7fc bumped requirements
  overnight; 1.15.1 lacks geo.Matrix — tags updated in step11+12).

## 3D — deliberately NOT included (be honest with the user)
gdk-ios has zero GdkGLContext implementation (pure Cairo/CoreAnimation);
rayforge sim3d = Gtk.GLArea + PyOpenGL + desktop GLSL. Enabling 3D means
writing a GLES/EAGL (or ANGLE/Metal) context in the C backend, a
PyOpenGL-on-iOS loading story, and shader porting — a multi-session
project requiring device iterations. Shipping it blind into a final
build risked a startup crash; it stays cleanly disabled
(RAYFORGE_DISABLE_3D).

## Architecture (unchanged)
ESP32 DevKit V1 BT-Classic<->TCP:23 relay (rayforge-laser.local,
firmware v3.4, huge-app partition, BT before WiFi, bonded-MAC
reconnect); ESP32-CAM side fire-watch (rayforge-cam.local, :81/stream,
:80/jpg). One BT master only. No wires between ESPs (hard requirement).

## Operating rules (unchanged)
Validate everything locally on a FRESH upstream clone before push
(upstream moves FAST — re-clone before any future work; requirements
can shift overnight). ast/compileall/yaml/bash -n. step12 ~10-15 min
(+ Rust); step9 (~40 min) only for gdk-ios/adw-shims/scripts. The
"[14/16] Publish diagnostics" failure is cosmetic; release publishing
= success. Tokens are per-session; never bake into logs.

## If a future session reopens this
- Partial-toolpath-coloring raster bug: superseded by vector drawing
  for vector jobs; if seen on raster engraves, P29 'view render
  complete' log lines diagnose it.
- Main-loop starvation (heartbeat 24-33 s under load) still exists;
  consequences defused but the pump could be improved.
- Backlog: 3D (see above), real OpenCV/ChArUco, signed .ipa (needs
  user's cert + provisioning as repo secrets).
