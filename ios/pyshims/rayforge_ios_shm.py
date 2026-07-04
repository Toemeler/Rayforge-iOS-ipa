"""In-process drop-in for multiprocessing.shared_memory on iOS.

iOS-CPython ships no _posixshmem (no POSIX shared memory on iOS), but in
Rayforge's iOS build all "workers" are threads in one process (see
rayforge_ios_pool), so shared memory degenerates to a name-keyed
in-process buffer registry. This module mirrors the exact subset of the
stdlib API Rayforge uses:

    SharedMemory(name=None, create=False, size=0)  -> .name .buf .size
    .close()   — drops this handle's buffer view
    .unlink()  — removes the block from the registry

Semantics matched to the stdlib where Rayforge depends on them:
  * attaching to an unknown name raises FileNotFoundError (view_runner
    catches exactly that for the unlink race)
  * create=True with an existing name raises FileExistsError
  * buffers outlive close() until unlink() (refcount-free, GC'd with the
    registry entry), matching the single-process reading of POSIX shm

Installed by ios_main.py via sys.modules['multiprocessing.shared_memory'].
"""

import secrets
import threading

_registry: dict = {}
_lock = threading.Lock()


class SharedMemory:
    def __init__(self, name=None, create=False, size=0, track=True):
        if create:
            if size <= 0:
                raise ValueError("'size' must be a positive number "
                                 "different from zero")
            if name is None:
                name = "ios_shm_" + secrets.token_hex(8)
            with _lock:
                if name in _registry:
                    raise FileExistsError(17, "File exists", name)
                _registry[name] = bytearray(size)
        else:
            if name is None:
                raise ValueError("'name' can only be None if create=True")
            with _lock:
                if name not in _registry:
                    raise FileNotFoundError(2, "No such file or directory",
                                            name)
        self._name = name
        self._closed = False

    @property
    def name(self):
        return self._name

    @property
    def size(self):
        with _lock:
            block = _registry.get(self._name)
        if block is None:
            return 0
        return len(block)

    @property
    def buf(self):
        if self._closed:
            return None
        with _lock:
            block = _registry.get(self._name)
        if block is None:
            raise FileNotFoundError(2, "No such file or directory",
                                    self._name)
        return memoryview(block)

    def close(self):
        self._closed = True

    def unlink(self):
        with _lock:
            _registry.pop(self._name, None)

    def __repr__(self):
        return f"IOSSharedMemory({self._name!r}, size={self.size})"


class ShareableList:  # pragma: no cover — not used by Rayforge
    def __init__(self, *a, **kw):
        raise NotImplementedError("ShareableList not supported in the iOS "
                                  "in-process shim")
