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
- **rayforge is now PINNED** in step12 (RAYFORGE_SHA=65684a3...) with
  raygeo v1.16.0. Upstream broke two builds in one day via requirement
  bumps landing between validation and build (geo.Matrix, then
  raygeo.image transparency fns -> all-white boot failure). Bump the
  pin only together with RAYGEO_TAG after a full local validation.

## 3D — ENABLED (user insisted; architecture chosen to avoid C changes)
NOT via GTK's GL plumbing (gdk-ios has no GdkGLContext; libepoxy 1.5.10
hardcodes macOS OpenGL.framework so it can never resolve GLES on iOS).
Instead:
- `OpenGL` pyshim is now a REAL ctypes GLES3 binding (OpenGLES.framework
  on device, Mesa libGLESv2 in the Linux validation env) implementing
  the exact PyOpenGL calling conventions sim3d uses (~45 fns; Gen/Delete
  flex args, numpy buffers, uniform arrays, GLError, GL.shaders
  compileShader/compileProgram/ShaderValidationError).
- `rayforge_ios_glarea.py` replaces Gtk.GLArea (attr swap pre-import,
  same pattern as FileDialog): Gtk.DrawingArea subclass + custom
  'render' signal, EAGLContext(ES3) via the filepicker's ObjC bridge,
  RGBA8+DEPTH16 renderbuffer FBO bound inside make_current(), pixels
  read back per frame -> premultiplied BGRA -> cairo paint. resize
  pre-handler keeps context/FBO current before Canvas3D's handlers.
- RAYFORGE_DISABLE_3D removed in ios_main. Upstream gl_utils already
  auto-selects '#version 300 es' headers when GL_VERSION says ES.
Validated on a LIVE Mesa ES3.2 surfaceless context: rayforge's real
Shader class compiles/links with ES headers; VAO/VBO/uniform/draw/
readback lit-pixel test green; FBO lifecycle + cairo conversion green.
Untested on device: EAGL context creation + CoreAnimation interplay
(everything else exercised for real). If 3D misbehaves on device, the
first log lines to check: 'GLArea: ES3 context created' /
'GLArea make_current failed' / 'GLArea draw failed' — failures flip a
per-widget _failed latch (blank 3D pane, app unaffected).

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
