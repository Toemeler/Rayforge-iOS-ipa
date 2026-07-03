#!/usr/bin/env python3
"""Rewrite every shared-library entry in a .gir to @rpath/<leaf>.

Typelibs record each namespace's shared-library string verbatim;
girepository g_module_open()s it at runtime. Absolute build-prefix paths
would make dyld load a SECOND copy of the stack next to the app's
bundled dylibs (two libgobject instances -> GType chaos), so the app
bundle recompiles typelibs from girs rewritten by this script:
@rpath/<name> resolves through the executable's rpath and dyld dedupes
onto the already-loaded bundle copy.

Handles comma-separated multi-library lists (e.g. GLib's
"libglib-2.0.0.dylib,libgobject-2.0.0.dylib") and leaves non-dylib
entries untouched.

Usage: fix-gir-sharedlib.py <in.gir> <out.gir>
"""
import re
import sys
from pathlib import Path


def fix_entry(entry: str) -> str:
    entry = entry.strip()
    if not entry:
        return entry
    leaf = entry.rsplit("/", 1)[-1]
    if leaf.endswith(".dylib"):
        return f"@rpath/{leaf}"
    return entry


def main() -> int:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    text = src.read_text()

    def repl(m: re.Match) -> str:
        libs = m.group(1).split(",")
        return 'shared-library="' + ",".join(fix_entry(e) for e in libs) + '"'

    fixed = re.sub(r'shared-library="([^"]*)"', repl, text)
    dst.write_text(fixed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
