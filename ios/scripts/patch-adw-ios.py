#!/usr/bin/env python3
"""Patch an extracted libadwaita source tree for the iOS build.

libadwaita gates its Apple support on host_machine.system() == 'darwin'
and #ifdef __APPLE__, both of which are true for iOS but reach for
AppKit (macOS-only). Three anchor-verified patches redirect iOS to the
portable code paths:

  P1 meson.build          skip the appleframeworks(AppKit) dependency
  P2 src/meson.build      compile the portal settings impl instead of
                          adw-settings-impl-macos.c (AppKit)
  P3 src/adw-settings.c   dispatch to the portal impl at runtime (the
                          portal impl degrades gracefully without a
                          session bus; gsettings/legacy fallbacks are
                          schema-guarded)

Usage: patch-adw-ios.py <adw-source-dir>

Idempotent: re-running on a patched tree succeeds without changes.
Exits non-zero (with a message) if any anchor is missing, so a
libadwaita version bump that moves the code is caught at patch time,
not as a mysterious compile error.
"""

import sys
from pathlib import Path

PATCHES = [
    # (file, old, new)
    (
        "meson.build",
        "if target_system == 'darwin'\n"
        "  appleframework_modules = [",
        "if target_system == 'darwin-disabled-for-ios'\n"
        "  appleframework_modules = [",
    ),
    (
        "src/meson.build",
        "if target_system == 'darwin'\n"
        "  libadwaita_deps += appleframeworks_dep",
        "if target_system == 'darwin-disabled-for-ios'\n"
        "  libadwaita_deps += appleframeworks_dep",
    ),
    (
        "src/adw-settings.c",
        "#ifdef __APPLE__\n"
        "  self->platform_impl = adw_settings_impl_macos_new",
        "#if defined(__APPLE__) && !defined(GDK_WINDOWING_IOS) && 0 /* iOS: portal fallback */\n"
        "  self->platform_impl = adw_settings_impl_macos_new",
    ),
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    if not (root / "meson.build").is_file():
        print(f"error: {root} does not look like a libadwaita tree")
        return 1

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
        print(f"patched: {rel}")

    print("libadwaita iOS patches applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
