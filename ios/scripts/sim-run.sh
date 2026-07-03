#!/usr/bin/env bash
# sim-run.sh — meson exe_wrapper for the iOS *simulator* cross build.
#
# g-ir-scanner (GObject-Introspection) compiles small "dumper" binaries
# for the target and must RUN them to extract type information. On the
# iOS simulator this is actually possible: `simctl spawn` executes any
# simulator-arch binary inside a booted simulator, sharing the host
# filesystem, so the dumper can read/write build-tree files directly.
#
# Requirements (exported by the workflow):
#   SIM_UDID                          — a *booted* simulator's UDID
#   SIMCTL_CHILD_DYLD_LIBRARY_PATH    — so dumpers find libgtk-4.dylib etc.
set -euo pipefail
: "${SIM_UDID:?SIM_UDID must be set to a booted simulator UDID}"
exec xcrun simctl spawn "${SIM_UDID}" "$@"
