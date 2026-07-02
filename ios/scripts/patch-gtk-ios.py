#!/usr/bin/env python3
"""
patch-gtk-ios.py — registers the GDK iOS backend in an extracted GTK
source tree. Idempotent; every patch verifies its anchor exists and its
result applied, exiting non-zero on any failure.

Usage: patch-gtk-ios.py <gtk-src-dir> <gdk-ios-src-dir>
"""

import shutil
import sys
from pathlib import Path


def patch(path: Path, anchor: str, replacement: str, marker: str) -> None:
    text = path.read_text()
    if marker in text:
        print(f"[patch-gtk-ios] {path.name}: already patched")
        return
    if anchor not in text:
        sys.exit(f"[patch-gtk-ios] FATAL: anchor not found in {path}:\n{anchor}")
    path.write_text(text.replace(anchor, replacement, 1))
    if marker not in path.read_text():
        sys.exit(f"[patch-gtk-ios] FATAL: marker missing after patching {path}")
    print(f"[patch-gtk-ios] {path.name}: patched")


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    gtk = Path(sys.argv[1])
    backend = Path(sys.argv[2])

    # 0. Copy backend sources into gdk/ios/
    dest = gtk / "gdk" / "ios"
    dest.mkdir(parents=True, exist_ok=True)
    for f in backend.iterdir():
        if f.is_file():
            shutil.copy2(f, dest / f.name)
    print(f"[patch-gtk-ios] copied {len(list(dest.iterdir()))} files to gdk/ios/")

    # 1. meson.options: new ios-backend option
    patch(
        gtk / "meson.options",
        "option('android-backend',\n"
        "       type: 'boolean',\n"
        "       value: true,\n"
        "       description : 'Enable the Android gdk backend (only when building on Android)')\n",
        "option('android-backend',\n"
        "       type: 'boolean',\n"
        "       value: true,\n"
        "       description : 'Enable the Android gdk backend (only when building on Android)')\n"
        "\n"
        "option('ios-backend',\n"
        "       type: 'boolean',\n"
        "       value: false,\n"
        "       description : 'Enable the iOS gdk backend (only when building for iOS)')\n",
        "ios-backend",
    )

    # 2. top-level meson.build: ios_enabled + platform gating
    patch(
        gtk / "meson.build",
        "android_enabled  = get_option('android-backend')\n",
        "android_enabled  = get_option('android-backend')\n"
        "ios_enabled      = get_option('ios-backend')\n",
        "ios_enabled      = get_option('ios-backend')",
    )
    patch(
        gtk / "meson.build",
        "if os_android\n"
        "  wayland_enabled = false\n"
        "  x11_enabled = false\n"
        "else\n"
        "  android_enabled = false\n"
        "endif\n",
        "if os_android\n"
        "  wayland_enabled = false\n"
        "  x11_enabled = false\n"
        "else\n"
        "  android_enabled = false\n"
        "endif\n"
        "\n"
        "# The iOS backend is darwin-only; it coexists with os_darwin but\n"
        "# replaces the macos backend.\n"
        "if not os_darwin\n"
        "  ios_enabled = false\n"
        "endif\n"
        "if ios_enabled\n"
        "  macos_enabled = false\n"
        "endif\n",
        "The iOS backend is darwin-only",
    )

    # 3. gdk/meson.build: backend list + windowing define
    patch(
        gtk / "gdk" / "meson.build",
        "foreach backend : ['android', 'broadway', 'wayland', 'win32', 'x11', 'macos']\n",
        "foreach backend : ['android', 'broadway', 'wayland', 'win32', 'x11', 'macos', 'ios']\n",
        "'macos', 'ios']",
    )
    patch(
        gtk / "gdk" / "meson.build",
        "gdkconfig_cdata.set('GDK_WINDOWING_MACOS', macos_enabled)\n",
        "gdkconfig_cdata.set('GDK_WINDOWING_MACOS', macos_enabled)\n"
        "gdkconfig_cdata.set('GDK_WINDOWING_IOS', ios_enabled)\n",
        "GDK_WINDOWING_IOS', ios_enabled",
    )

    # 4. gdk/gdkconfig.h.meson: mesondefine
    patch(
        gtk / "gdk" / "gdkconfig.h.meson",
        "#mesondefine GDK_WINDOWING_MACOS\n",
        "#mesondefine GDK_WINDOWING_MACOS\n"
        "#mesondefine GDK_WINDOWING_IOS\n",
        "#mesondefine GDK_WINDOWING_IOS",
    )

    # 5. gdk/gdkdisplaymanager.c: prototype + backend registration.
    #    A bare prototype avoids pulling the backend's private include
    #    chain into the display manager.
    patch(
        gtk / "gdk" / "gdkdisplaymanager.c",
        "#ifdef GDK_WINDOWING_MACOS\n"
        "#include \"macos/gdkmacosdisplay-private.h\"\n"
        "#endif\n",
        "#ifdef GDK_WINDOWING_MACOS\n"
        "#include \"macos/gdkmacosdisplay-private.h\"\n"
        "#endif\n"
        "\n"
        "#ifdef GDK_WINDOWING_IOS\n"
        "GdkDisplay *_gdk_ios_display_open (const char *display_name);\n"
        "#endif\n",
        "_gdk_ios_display_open (const char *display_name);",
    )
    patch(
        gtk / "gdk" / "gdkdisplaymanager.c",
        "#ifdef GDK_WINDOWING_MACOS\n"
        "  { \"macos\",   _gdk_macos_display_open },\n"
        "#endif\n",
        "#ifdef GDK_WINDOWING_IOS\n"
        "  { \"ios\",     _gdk_ios_display_open },\n"
        "#endif\n"
        "#ifdef GDK_WINDOWING_MACOS\n"
        "  { \"macos\",   _gdk_macos_display_open },\n"
        "#endif\n",
        '{ "ios",     _gdk_ios_display_open },',
    )

    print("[patch-gtk-ios] all patches applied OK")


if __name__ == "__main__":
    main()
