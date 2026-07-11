"""Gtk.GLArea replacement for iOS.

GTK on iOS has no GdkGLContext (backend is pure Cairo) and libepoxy
cannot resolve GLES on iOS, so the stock GLArea path is unusable. This
module provides an API-compatible GLArea built on Gtk.DrawingArea:

  * context: EAGLContext (OpenGL ES 3) created via the ObjC runtime
    (same ctypes bridge as the native file picker); in the Linux
    validation environment a surfaceless-EGL context is used instead.
  * rendering: an offscreen FBO (RGBA8 + DEPTH16 renderbuffers) sized
    to the widget; make_current() binds both the context and the FBO,
    so client code that assumes "the GLArea framebuffer is bound" just
    works.
  * display: after emitting the 'render' signal, pixels are read back
    and painted into the widget's cairo context (RGBA bottom-up ->
    premultiplied BGRA top-down).

API surface implemented (everything rayforge's Canvas3D touches):
signals 'render' and 'resize' (DrawingArea already emits ::resize),
make_current(), queue_render(), set_has_depth_buffer(), plus inherited
Widget methods. Unknown GLArea setters are accepted as no-ops.
"""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)



class _EAGLContext:
    """OpenGL ES 3 context via EAGL (ObjC runtime)."""

    def __init__(self):
        from rayforge_ios_filepicker import _cls, _load_objc, _msg

        _load_objc()
        self._msg = _msg
        # kEAGLRenderingAPIOpenGLES3 == 3
        ctx = _msg(
            _msg(_cls("EAGLContext"), "alloc"),
            "initWithAPI:", 3,
            argtypes=[ctypes.c_long],
        )
        if not ctx:
            raise RuntimeError("EAGLContext(ES3) init failed")
        self._ctx = ctx
        self._cls_ctx = _cls("EAGLContext")

    def make_current(self):
        ok = self._msg(
            self._cls_ctx, "setCurrentContext:", self._ctx,
            restype=ctypes.c_bool,
        )
        if not ok:
            raise RuntimeError("EAGLContext setCurrentContext failed")


class _EGLContext:
    """Surfaceless-EGL ES3 context (Linux validation only)."""

    def __init__(self):
        c = ctypes
        P = c.POINTER
        egl = c.CDLL("libEGL.so.1")
        spec = [
            ("eglGetPlatformDisplay", c.c_void_p,
             [c.c_uint, c.c_void_p, c.c_void_p]),
            ("eglInitialize", c.c_uint,
             [c.c_void_p, P(c.c_int), P(c.c_int)]),
            ("eglBindAPI", c.c_uint, [c.c_uint]),
            ("eglChooseConfig", c.c_uint,
             [c.c_void_p, P(c.c_int), P(c.c_void_p), c.c_int,
              P(c.c_int)]),
            ("eglCreateContext", c.c_void_p,
             [c.c_void_p, c.c_void_p, c.c_void_p, P(c.c_int)]),
            ("eglMakeCurrent", c.c_uint, [c.c_void_p] * 4),
        ]
        for n, r, a in spec:
            f = getattr(egl, n)
            f.restype = r
            f.argtypes = a
        dpy = egl.eglGetPlatformDisplay(0x31DD, None, None)
        maj, mn = c.c_int(), c.c_int()
        if not egl.eglInitialize(dpy, c.byref(maj), c.byref(mn)):
            raise RuntimeError("eglInitialize failed")
        egl.eglBindAPI(0x30A0)
        attrs = (c.c_int * 5)(0x3040, 0x0040, 0x3033, 0, 0x3038)
        cfgs = (c.c_void_p * 1)()
        n = c.c_int()
        if not (
            egl.eglChooseConfig(dpy, attrs, cfgs, 1, c.byref(n))
            and n.value
        ):
            raise RuntimeError("eglChooseConfig failed")
        ctx = egl.eglCreateContext(
            dpy, cfgs[0], None, (c.c_int * 3)(0x3098, 3, 0x3038)
        )
        if not ctx:
            raise RuntimeError("eglCreateContext failed")
        self._egl, self._dpy, self._ctx = egl, dpy, ctx

    def make_current(self):
        if not self._egl.eglMakeCurrent(
            self._dpy, None, None, self._ctx
        ):
            raise RuntimeError("eglMakeCurrent failed")


def _new_context():
    try:
        return _EAGLContext()
    except Exception:
        return _EGLContext()


class _FboTarget:
    """RGBA8+DEPTH16 renderbuffer FBO, resized on demand."""

    GL_RGBA8 = 0x8058

    def __init__(self):
        self.fbo = None
        self.color = None
        self.depth = None
        self.w = 0
        self.h = 0

    def ensure(self, GL, w, h):
        w = max(1, int(w))
        h = max(1, int(h))
        if self.fbo is not None and (w, h) == (self.w, self.h):
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
            return
        self.release(GL)
        self.fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        self.color = GL.glGenRenderbuffers(1)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self.color)
        GL.glRenderbufferStorage(
            GL.GL_RENDERBUFFER, self.GL_RGBA8, w, h
        )
        GL.glFramebufferRenderbuffer(
            GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
            GL.GL_RENDERBUFFER, self.color,
        )
        self.depth = GL.glGenRenderbuffers(1)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self.depth)
        GL.glRenderbufferStorage(
            GL.GL_RENDERBUFFER, GL.GL_DEPTH_COMPONENT16, w, h
        )
        GL.glFramebufferRenderbuffer(
            GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT,
            GL.GL_RENDERBUFFER, self.depth,
        )
        status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
        if status != GL.GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"FBO incomplete: 0x{status:x}")
        self.w, self.h = w, h

    def release(self, GL):
        try:
            if self.color is not None:
                GL.glDeleteRenderbuffers(1, [self.color])
            if self.depth is not None:
                GL.glDeleteRenderbuffers(1, [self.depth])
            if self.fbo is not None:
                GL.glDeleteFramebuffers(1, [self.fbo])
        except Exception:
            pass
        self.fbo = self.color = self.depth = None
        self.w = self.h = 0


def rgba_to_cairo_argb(img):
    """RGBA (bottom-up rows from glReadPixels) -> premultiplied BGRA
    top-down bytes for cairo FORMAT_ARGB32 (little-endian)."""
    import numpy as np

    img = img[::-1]  # flip to top-down
    a = img[..., 3:4].astype(np.uint16)
    bgr = img[..., [2, 1, 0]].astype(np.uint16)
    prem = ((bgr * a + 127) // 255).astype(np.uint8)
    out = np.empty(img.shape[:2] + (4,), np.uint8)
    out[..., :3] = prem
    out[..., 3] = img[..., 3]
    return np.ascontiguousarray(out)


def install(Gtk, GObject, ioslog=lambda m: None):
    """Replace Gtk.GLArea with the DrawingArea-based emulation."""
    import cairo

    class IOSGLArea(Gtk.DrawingArea):
        __gsignals__ = {
            "render": (
                GObject.SignalFlags.RUN_LAST,
                bool,
                (object,),
            ),
        }

        def __init__(self):
            super().__init__()
            self._gl_ctx = None
            self._fbo = _FboTarget()
            self._failed = False
            self.set_draw_func(self._draw)
            # Runs before Canvas3D's own resize handler (connected in
            # its __init__ AFTER super().__init__()), so the context
            # and FBO are current when client resize code executes.
            self.connect("resize", self._pre_resize)

        # ------------------------------------------------ GLArea API
        def make_current(self):
            if self._failed:
                return
            try:
                if self._gl_ctx is None:
                    self._gl_ctx = _new_context()
                    ioslog("GLArea: ES3 context created")
                self._gl_ctx.make_current()
                from OpenGL import GL

                self._fbo.ensure(
                    GL, self.get_width(), self.get_height()
                )
            except Exception:
                self._failed = True
                logger.exception("GLArea make_current failed")

        def queue_render(self):
            self.queue_draw()

        def set_has_depth_buffer(self, v):
            pass

        def set_has_stencil_buffer(self, v):
            pass

        def set_auto_render(self, v):
            pass

        def set_required_version(self, a, b):
            pass

        def set_use_es(self, v):
            pass

        def get_error(self):
            return None

        def get_context(self):
            return self._gl_ctx

        def attach_buffers(self):
            self.make_current()

        # ------------------------------------------------- internals
        def _pre_resize(self, _area, w, h):
            self.make_current()

        def _draw(self, _area, cr, width, height):
            if self._failed:
                return
            try:
                self.make_current()
                from OpenGL import GL

                self.emit("render", None)
                GL.glFinish()
                img = GL.glReadPixels(
                    0, 0, self._fbo.w, self._fbo.h,
                    GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                )
                data = rgba_to_cairo_argb(img)
                surf = cairo.ImageSurface.create_for_data(
                    memoryview(bytearray(data.tobytes())),
                    cairo.FORMAT_ARGB32,
                    self._fbo.w,
                    self._fbo.h,
                    self._fbo.w * 4,
                )
                cr.set_source_surface(surf, 0, 0)
                cr.paint()
            except Exception:
                self._failed = True
                logger.exception("GLArea draw failed")

    Gtk.GLArea = IOSGLArea
    ioslog("iOS GLArea (EAGL/FBO) installed")
    return True
