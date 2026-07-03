#!/usr/bin/env bash
# sim-spawn.sh — binary wrapper for g-ir-scanner dumpers that link UIKit
# (Gdk/Gsk/Gtk/Adw). Unlike plain GLib dumpers, these cannot run as bare
# macOS processes even with DYLD_ROOT_PATH: UIKit's initializers require
# a real simulator process context and the kernel SIGKILLs them
# otherwise. `simctl spawn` provides that context; the scanner invokes
# the dumper with absolute paths, so the lost working directory does not
# matter here.
set -euo pipefail
: "${SIM_UDID:?SIM_UDID must be set to a booted simulator UDID}"
# Dumpers link the freshly built gtk/adw dylibs from the build trees and
# the rest of the stack from the prefix.
export SIMCTL_CHILD_DYLD_LIBRARY_PATH="${GITHUB_WORKSPACE}/gtk-build/gtk:${GITHUB_WORKSPACE}/adw-build/src:${GITHUB_WORKSPACE}/ios-out/lib${SIMCTL_CHILD_DYLD_LIBRARY_PATH:+:${SIMCTL_CHILD_DYLD_LIBRARY_PATH}}"
exec xcrun simctl spawn "${SIM_UDID}" "$@"
