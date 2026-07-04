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
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    if not (root / "rayforge").is_dir():
        print(f"error: {root} does not look like a rayforge tree")
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
        print(f"patched: {rel} ({old.splitlines()[0][:50]}...)")

    print("rayforge iOS patches applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
