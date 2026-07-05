"""iOS stub for PyOpenGL.

Real PyOpenGL dlopen()s the desktop GLX / libGL library at import time
(OpenGL.platform._load). iOS has no desktop OpenGL, so `from OpenGL
import GL` raises OSError -> ImportError. Rayforge's 3D canvas is only
guarded in ui_gtk/sim3d/__init__.py; the *renderer* modules
(sim3d/renderer/model_renderer.py, sim3d/gl_utils.py) import OpenGL at
module top level and are pulled in unconditionally by the machine
settings dialog (laser_preferences_page.py). That import therefore
unwinds out of Application.do_activate() before the main window is ever
built -> zero windows -> black screen.

This stub makes every ``OpenGL`` / ``OpenGL.*`` import succeed with inert
objects so the rest of the UI can build. No actual GL is executed at
import time by those modules (all GL calls live inside methods that only
run while rendering the 3D canvas). The 3D canvas is additionally kept
disabled via RAYFORGE_DISABLE_3D, so none of these inert GL calls ever
run. Real GL on iOS is a later phase (Metal/ANGLE), not desktop GLX.
"""

import sys
import types
import importlib.abc
import importlib.machinery


class _Dummy:
    """Inert stand-in: callable, subscriptable, attribute-transparent."""

    def __call__(self, *args, **kwargs):
        return _dummy

    def __getattr__(self, name):
        return _dummy

    def __getitem__(self, key):
        return _dummy

    def __iter__(self):
        return iter(())

    def __int__(self):
        return 0

    def __index__(self):
        return 0

    def __float__(self):
        return 0.0

    def __bool__(self):
        return False

    def __repr__(self):
        return "<OpenGL-ios-stub>"


_dummy = _Dummy()


def _stub_getattr(name):
    return _dummy


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        mod = types.ModuleType(spec.name)
        # Mark as a package so nested submodule imports keep resolving.
        mod.__path__ = []
        mod.__getattr__ = _stub_getattr
        return mod

    def exec_module(self, module):
        pass


class _OpenGLFinder(importlib.abc.MetaPathFinder):
    _loader = _StubLoader()

    def find_spec(self, fullname, path=None, target=None):
        # Only synthesize submodules; this package's own __init__ (this
        # file) is loaded normally by the path finder.
        if fullname.startswith("OpenGL."):
            return importlib.machinery.ModuleSpec(
                fullname, self._loader, is_package=True
            )
        return None


if not any(isinstance(f, _OpenGLFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _OpenGLFinder())


# Any attribute directly off the OpenGL package resolves to the inert
# stand-in too (e.g. `import OpenGL; OpenGL.GL_TRUE`).
def __getattr__(name):
    return _dummy
