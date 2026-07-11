"""Real GLES 3.0 binding for iOS (replaces the Phase-1 inert stub).

Loads OpenGLES.framework via ctypes on device (Mesa's libGLESv2 in the
Linux validation environment) and exposes the PyOpenGL calling
conventions rayforge's sim3d actually uses. Context creation lives in
rayforge_ios_glarea (EAGL / EGL); this package only wraps GL entry
points, so importing it never touches a display.
"""
from . import GL  # noqa: F401

__version__ = "ios-gles-1.0"
