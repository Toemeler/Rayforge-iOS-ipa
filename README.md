# Rayforge iOS (iPad) build

Native iOS/iPadOS build of [Rayforge](https://github.com/barebaric/rayforge)
— the GTK4/Libadwaita laser cutter & engraver software — running the actual
unmodified Rayforge Python/`ui_gtk` code on device, driven by mouse and
keyboard (iPad trackpad/mouse + hardware keyboard), with no streaming and no
virtualization.

This is built incrementally through GitHub Actions workflows. Each step
produces a **downloadable artifact** so it can be verified before moving on to
the next dependency in the stack.

## Why it's staged

GTK4 has no iOS backend upstream, so the port is built bottom-up:

1. Cross-compile the GTK dependency stack for iOS `arm64`
   (glib → cairo/pango/graphene/harfbuzz → gdk-pixbuf/librsvg → gtk4 →
   libadwaita).
2. Add a GDK iOS windowing/input backend (UIKit surface + Metal renderer +
   trackpad/mouse/keyboard event mapping).
3. Embed CPython (BeeWare Python-Apple-support) + PyGObject bound to the
   cross-compiled libs.
4. Cross-compile the remaining Rayforge Python deps
   (numpy, scipy, opencv, pymupdf, pyvips, ezdxf, pypdf, trimesh; plus the
   Rust libs vtracer + raygeo via `cargo build --target aarch64-apple-ios`).
5. Swap `shared/tasker`'s multiprocessing for a thread pool (iOS forbids
   `fork()`).
6. Keep network machine transports as-is; route serial/USB via CoreBluetooth /
   ExternalAccessory.
7. Bundle + sign + produce the `.ipa`.

## Steps / workflows

| Step | Workflow | Produces | Status |
| ---- | -------- | -------- | ------ |
| 1 | `ios-step1-glib.yml` | `glib-ios-arm64` (static libs) | ✅ done |
| 2 | `ios-step2-cairo-pango.yml` | `cairo-pango-ios-arm64` (full rendering+text stack) | ✅ done |
| 3 | `ios-step3-pixbuf-graphene.yml` | `gtk-deps-ios-arm64` (+jpeg-turbo, graphene, gdk-pixbuf) | ✅ done |
| 4 | `ios-step4-gtk.yml` | `gtk4-ios-arm64` — **GTK 4.22.4 (libgtk-4.1.dylib) built for iOS arm64** | ✅ done |
| 5 | `ios-step5-gtk-ios-backend.yml` | GDK iOS backend (UIKit surface, touch/pointer/keyboard input, cairo renderer) compiled + linked into libgtk | ✅ done |
| 6 | `ios-step6-simulator-test.yml` | **GTK 4 app running in the iOS simulator** (.app bundle, launch, screenshot) — a world first | ✅ done |
| 7 | `ios-step7-libadwaita.yml` | **Libadwaita 1.9.1 running on iOS** — AdwApplication via `gdk_ios_application_run()`, AppKit-free patches, appstream stub | ✅ done |
| 8 | `ios-step8-python.yml` | **CPython 3.13.14 running natively on iOS** (sys.platform=ios) inside the Adw app | ✅ done |
| 9 | `ios-step9-introspection.yml` | GObject-Introspection stack (typelibs via simctl-spawn exe_wrapper) | 🔨 in progress |
| 10 | PyGObject + pycairo cross-compiled against the prefix | | 🔜 next |

Key fixes encoded along the way: pkg-config sysroot isolation
(`PKG_CONFIG_SYSROOT_DIR=`), SDK zlib via synthesized `zlib.pc`, libpng/expat/
libjpeg-turbo/libtiff via CMake iOS toolchain (`CMAKE_SYSTEM_PROCESSOR=aarch64`),
freetype↔harfbuzz 3-pass build, fontconfig ≥ 2.17 for pango 1.58, cairo quartz
backend off (macOS-only frameworks), pcre2 JIT off (forbidden on iOS anyway),
iOS Mach-O host-tool purge + `.pc` tool-var redirect to native brew tools, GTK
patches P1 (iOS SDK version gate) and P2 (colorpicker quartz guard — sole
undefined symbol in the whole libgtk link).

## How to run and test Step 1

1. Go to the repo **Actions** tab.
2. Select **"iOS Step 1 - Build GLib (arm64)"**.
3. Click **Run workflow** (optionally override the GLib version or iOS min).
4. When it finishes, download the `glib-ios-arm64` artifact.

### What a successful Step 1 looks like

The `[7/8] Build + install GLib` step prints the built static libraries and
runs `lipo -info` on each. You should see:

- `libglib-2.0.a`, `libgobject-2.0.a`, `libgio-2.0.a`, `libgmodule-2.0.a`
  (and `libgthread-2.0.a`) under `ios-out/lib/`.
- Each reporting architecture **`arm64`** (via `lipo -info`).
- `.pc` pkg-config files under `ios-out/lib/pkgconfig/`.

If it fails, download the **`step1-logs`** artifact — it contains
`meson-setup.log`, `glib-build.log`, `glib-install.log`, the generated
`ios-arm64-cross.txt`, and meson's own `meson-log.txt` — and share it.

## On-device logging (for testing the eventual app on iPad)

`ios/scripts/ios_logging.py` is bundled into the app. On launch it redirects
stdout/stderr, the Python `logging` framework, and native crash tracebacks
(via `faulthandler`) into:

```
<App Documents>/rayforge-ios.log
```

With `UIFileSharingEnabled` + `LSSupportsOpeningDocumentsInPlace` set in the
app's `Info.plist`, this file is visible in the iOS **Files** app under the
Rayforge folder. If anything fails on device, grab that log and send it back.

## Shared build tooling

- `ios/scripts/gen-cross-file.sh` — generates the Meson `arm64` iOS cross file
  from the installed Xcode iOS SDK. Reused by every native-dependency build.
