#!/usr/bin/env bash
# sim-run.sh — meson exe_wrapper for the iOS *simulator* cross build.
#
# Simulator CLI binaries execute natively on macOS when DYLD_ROOT_PATH
# points at the simulator runtime root — no simctl needed. Direct
# execution preserves the working directory (build tools like
# gi-compile-repository are invoked with relative paths) and the full
# environment, which `simctl spawn` does not.
#
# DYLD_ROOT_PATH is normally exported by the workflow; as a fallback we
# derive it from the newest available iOS runtime.
set -euo pipefail

if [ -z "${DYLD_ROOT_PATH:-}" ]; then
  DYLD_ROOT_PATH=$(xcrun simctl list runtimes -j | python3 -c "import json,sys; rs=[r for r in json.load(sys.stdin)['runtimes'] if r.get('platform')=='iOS' and r.get('isAvailable')]; print(rs[-1]['runtimeRoot'])")
  export DYLD_ROOT_PATH
fi

exec "$@"
