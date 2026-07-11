"""GLES 3.0 via ctypes, PyOpenGL-compatible for rayforge's sim3d."""

import ctypes
import os
import sys

import numpy as np

# ------------------------------------------------------------ library
_CANDIDATES = [
    os.environ.get("RAYFORGE_GLES_LIB") or "",
    "/System/Library/Frameworks/OpenGLES.framework/OpenGLES",  # iOS
    "libGLESv2.so.2",  # Linux validation (Mesa)
    "libGLESv2.so",
]
_lib = None
for _c in _CANDIDATES:
    if not _c:
        continue
    if _c.startswith("/") and not os.path.exists(_c):
        continue
    try:
        _lib = ctypes.CDLL(_c)
        break
    except OSError:
        continue
if _lib is None:
    raise ImportError("no GLES library available")

# ---------------------------------------------------------- constants
GL_FALSE = 0
GL_TRUE = 1
GL_POINTS = 0x0000
GL_LINES = 0x0001
GL_LINE_STRIP = 0x0003
GL_TRIANGLES = 0x0004
GL_TRIANGLE_STRIP = 0x0005
GL_TRIANGLE_FAN = 0x0006
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_COLOR_BUFFER_BIT = 0x00004000
GL_BLEND = 0x0BE2
GL_DEPTH_TEST = 0x0B71
GL_LEQUAL = 0x0203
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_ONE = 1
GL_FLOAT = 0x1406
GL_UNSIGNED_BYTE = 0x1401
GL_UNSIGNED_INT = 0x1405
GL_VERSION = 0x1F02
GL_VENDOR = 0x1F00
GL_RENDERER = 0x1F01
GL_MAX_TEXTURE_SIZE = 0x0D33
GL_UNPACK_ALIGNMENT = 0x0CF5
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE0 = 0x84C0
GL_TEXTURE1 = 0x84C1
GL_TEXTURE_MAG_FILTER = 0x2800
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_NEAREST = 0x2600
GL_LINEAR = 0x2601
GL_CLAMP_TO_EDGE = 0x812F
GL_RGBA = 0x1908
GL_RED = 0x1903
GL_R8 = 0x8229
GL_RGBA32F = 0x8814
GL_ARRAY_BUFFER = 0x8892
GL_ELEMENT_ARRAY_BUFFER = 0x8893
GL_STATIC_DRAW = 0x88E4
GL_DYNAMIC_DRAW = 0x88E8
GL_FRAGMENT_SHADER = 0x8B30
GL_VERTEX_SHADER = 0x8B31
GL_COMPILE_STATUS = 0x8B81
GL_LINK_STATUS = 0x8B82
GL_VALIDATE_STATUS = 0x8B83
GL_INFO_LOG_LENGTH = 0x8B84
GL_ALIASED_LINE_WIDTH_RANGE = 0x846E
GL_FRAMEBUFFER = 0x8D40
GL_RENDERBUFFER = 0x8D41
GL_COLOR_ATTACHMENT0 = 0x8CE0
GL_DEPTH_ATTACHMENT = 0x8D00
GL_DEPTH_COMPONENT16 = 0x81A5
GL_DEPTH_COMPONENT24 = 0x81A6
GL_FRAMEBUFFER_COMPLETE = 0x8CD5
GL_NO_ERROR = 0

_INT_PNAMES_N = {
    GL_ALIASED_LINE_WIDTH_RANGE: 2,
}


class GLError(Exception):
    pass


Error = GLError

_c = ctypes
_p = _c.POINTER


def _fn(name, restype, *argtypes):
    f = getattr(_lib, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


_glGetError = _fn("glGetError", _c.c_uint)
_glGetString = _fn("glGetString", _c.c_char_p, _c.c_uint)
_glGetIntegerv = _fn("glGetIntegerv", None, _c.c_uint, _p(_c.c_int))
_glGetFloatv = _fn("glGetFloatv", None, _c.c_uint, _p(_c.c_float))
_glEnable = _fn("glEnable", None, _c.c_uint)
_glDisable = _fn("glDisable", None, _c.c_uint)
_glBlendFunc = _fn("glBlendFunc", None, _c.c_uint, _c.c_uint)
_glDepthFunc = _fn("glDepthFunc", None, _c.c_uint)
_glDepthMask = _fn("glDepthMask", None, _c.c_ubyte)
_glClearColor = _fn(
    "glClearColor", None, _c.c_float, _c.c_float, _c.c_float, _c.c_float
)
_glClear = _fn("glClear", None, _c.c_uint)
_glViewport = _fn(
    "glViewport", None, _c.c_int, _c.c_int, _c.c_int, _c.c_int
)
_glLineWidth = _fn("glLineWidth", None, _c.c_float)
_glPixelStorei = _fn("glPixelStorei", None, _c.c_uint, _c.c_int)
_glGenBuffers = _fn("glGenBuffers", None, _c.c_int, _p(_c.c_uint))
_glDeleteBuffers = _fn("glDeleteBuffers", None, _c.c_int, _p(_c.c_uint))
_glBindBuffer = _fn("glBindBuffer", None, _c.c_uint, _c.c_uint)
_glBufferData = _fn(
    "glBufferData", None, _c.c_uint, _c.c_ssize_t, _c.c_void_p, _c.c_uint
)
_glBufferSubData = _fn(
    "glBufferSubData", None, _c.c_uint, _c.c_ssize_t, _c.c_ssize_t,
    _c.c_void_p,
)
_glGenVertexArrays = _fn(
    "glGenVertexArrays", None, _c.c_int, _p(_c.c_uint)
)
_glDeleteVertexArrays = _fn(
    "glDeleteVertexArrays", None, _c.c_int, _p(_c.c_uint)
)
_glBindVertexArray = _fn("glBindVertexArray", None, _c.c_uint)
_glEnableVertexAttribArray = _fn(
    "glEnableVertexAttribArray", None, _c.c_uint
)
_glVertexAttribPointer = _fn(
    "glVertexAttribPointer", None, _c.c_uint, _c.c_int, _c.c_uint,
    _c.c_ubyte, _c.c_int, _c.c_void_p,
)
_glDrawArrays = _fn(
    "glDrawArrays", None, _c.c_uint, _c.c_int, _c.c_int
)
_glGenTextures = _fn("glGenTextures", None, _c.c_int, _p(_c.c_uint))
_glDeleteTextures = _fn(
    "glDeleteTextures", None, _c.c_int, _p(_c.c_uint)
)
_glBindTexture = _fn("glBindTexture", None, _c.c_uint, _c.c_uint)
_glActiveTexture = _fn("glActiveTexture", None, _c.c_uint)
_glTexParameteri = _fn(
    "glTexParameteri", None, _c.c_uint, _c.c_uint, _c.c_int
)
_glTexImage2D = _fn(
    "glTexImage2D", None, _c.c_uint, _c.c_int, _c.c_int, _c.c_int,
    _c.c_int, _c.c_int, _c.c_uint, _c.c_uint, _c.c_void_p,
)
_glUseProgram = _fn("glUseProgram", None, _c.c_uint)
_glGetUniformLocation = _fn(
    "glGetUniformLocation", _c.c_int, _c.c_uint, _c.c_char_p
)
_glUniform1i = _fn("glUniform1i", None, _c.c_int, _c.c_int)
_glUniform1f = _fn("glUniform1f", None, _c.c_int, _c.c_float)
_glUniform2fv = _fn(
    "glUniform2fv", None, _c.c_int, _c.c_int, _p(_c.c_float)
)
_glUniform3fv = _fn(
    "glUniform3fv", None, _c.c_int, _c.c_int, _p(_c.c_float)
)
_glUniform4fv = _fn(
    "glUniform4fv", None, _c.c_int, _c.c_int, _p(_c.c_float)
)
_glUniformMatrix3fv = _fn(
    "glUniformMatrix3fv", None, _c.c_int, _c.c_int, _c.c_ubyte,
    _p(_c.c_float),
)
_glUniformMatrix4fv = _fn(
    "glUniformMatrix4fv", None, _c.c_int, _c.c_int, _c.c_ubyte,
    _p(_c.c_float),
)
_glCreateShader = _fn("glCreateShader", _c.c_uint, _c.c_uint)
_glDeleteShader = _fn("glDeleteShader", None, _c.c_uint)
_glShaderSource = _fn(
    "glShaderSource", None, _c.c_uint, _c.c_int, _p(_c.c_char_p),
    _p(_c.c_int),
)
_glCompileShader = _fn("glCompileShader", None, _c.c_uint)
_glGetShaderiv = _fn(
    "glGetShaderiv", None, _c.c_uint, _c.c_uint, _p(_c.c_int)
)
_glGetShaderInfoLog = _fn(
    "glGetShaderInfoLog", None, _c.c_uint, _c.c_int, _p(_c.c_int),
    _c.c_char_p,
)
_glCreateProgram = _fn("glCreateProgram", _c.c_uint)
_glDeleteProgram = _fn("glDeleteProgram", None, _c.c_uint)
_glAttachShader = _fn("glAttachShader", None, _c.c_uint, _c.c_uint)
_glLinkProgram = _fn("glLinkProgram", None, _c.c_uint)
_glValidateProgram = _fn("glValidateProgram", None, _c.c_uint)
_glGetProgramiv = _fn(
    "glGetProgramiv", None, _c.c_uint, _c.c_uint, _p(_c.c_int)
)
_glGetProgramInfoLog = _fn(
    "glGetProgramInfoLog", None, _c.c_uint, _c.c_int, _p(_c.c_int),
    _c.c_char_p,
)
_glGenFramebuffers = _fn(
    "glGenFramebuffers", None, _c.c_int, _p(_c.c_uint)
)
_glDeleteFramebuffers = _fn(
    "glDeleteFramebuffers", None, _c.c_int, _p(_c.c_uint)
)
_glBindFramebuffer = _fn(
    "glBindFramebuffer", None, _c.c_uint, _c.c_uint
)
_glGenRenderbuffers = _fn(
    "glGenRenderbuffers", None, _c.c_int, _p(_c.c_uint)
)
_glDeleteRenderbuffers = _fn(
    "glDeleteRenderbuffers", None, _c.c_int, _p(_c.c_uint)
)
_glBindRenderbuffer = _fn(
    "glBindRenderbuffer", None, _c.c_uint, _c.c_uint
)
_glRenderbufferStorage = _fn(
    "glRenderbufferStorage", None, _c.c_uint, _c.c_uint, _c.c_int,
    _c.c_int,
)
_glFramebufferRenderbuffer = _fn(
    "glFramebufferRenderbuffer", None, _c.c_uint, _c.c_uint, _c.c_uint,
    _c.c_uint,
)
_glCheckFramebufferStatus = _fn(
    "glCheckFramebufferStatus", _c.c_uint, _c.c_uint
)
_glReadPixels = _fn(
    "glReadPixels", None, _c.c_int, _c.c_int, _c.c_int, _c.c_int,
    _c.c_uint, _c.c_uint, _c.c_void_p,
)
_glFinish = _fn("glFinish", None)


# ------------------------------------------------- PyOpenGL semantics
def _gen(fn, n):
    arr = (_c.c_uint * n)()
    fn(n, arr)
    return arr[0] if n == 1 else list(arr)


def _delete(fn, a, b=None):
    # PyOpenGL accepts (n, ids) or (ids)
    ids = b if b is not None else a
    if isinstance(ids, (int, np.integer)):
        ids = [ids]
    ids = [int(i) for i in ids]
    arr = (_c.c_uint * len(ids))(*ids)
    fn(len(ids), arr)


def glGenBuffers(n=1):
    return _gen(_glGenBuffers, n)


def glDeleteBuffers(a, b=None):
    _delete(_glDeleteBuffers, a, b)


def glGenVertexArrays(n=1):
    return _gen(_glGenVertexArrays, n)


def glDeleteVertexArrays(a, b=None):
    _delete(_glDeleteVertexArrays, a, b)


def glGenTextures(n=1):
    return _gen(_glGenTextures, n)


def glDeleteTextures(a, b=None):
    _delete(_glDeleteTextures, a, b)


def glGenFramebuffers(n=1):
    return _gen(_glGenFramebuffers, n)


def glDeleteFramebuffers(a, b=None):
    _delete(_glDeleteFramebuffers, a, b)


def glGenRenderbuffers(n=1):
    return _gen(_glGenRenderbuffers, n)


def glDeleteRenderbuffers(a, b=None):
    _delete(_glDeleteRenderbuffers, a, b)


def _as_buffer(data):
    """(ptr, nbytes) for numpy/bytes/None keeping a ref alive."""
    if data is None:
        return None, 0, None
    if isinstance(data, (bytes, bytearray)):
        buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
        return ctypes.cast(buf, _c.c_void_p), len(data), buf
    a = np.ascontiguousarray(data)
    return a.ctypes.data_as(_c.c_void_p), a.nbytes, a


def glBufferData(target, *args):
    # (target, data, usage) or (target, size, data, usage)
    if len(args) == 2:
        data, usage = args
        ptr, size, keep = _as_buffer(data)
    else:
        size, data, usage = args
        ptr, _, keep = _as_buffer(data)
    _glBufferData(target, size, ptr, usage)


def glBufferSubData(target, offset, size, data=None):
    if data is None:
        data, size = size, None
    ptr, nbytes, keep = _as_buffer(data)
    _glBufferSubData(
        target, offset, size if size is not None else nbytes, ptr
    )


def glVertexAttribPointer(index, size, type_, normalized, stride, ptr):
    if ptr is None:
        ptr = 0
    if isinstance(ptr, int):
        ptr = _c.c_void_p(ptr)
    _glVertexAttribPointer(
        index, size, type_, 1 if normalized else 0, stride, ptr
    )


def glTexImage2D(
    target, level, internalformat, width, height, border, fmt, type_,
    data,
):
    ptr, _, keep = _as_buffer(data)
    _glTexImage2D(
        target, level, internalformat, width, height, border, fmt,
        type_, ptr,
    )


def glGetString(name):
    return _glGetString(name)


def glGetIntegerv(pname):
    n = _INT_PNAMES_N.get(pname, 1)
    arr = (_c.c_int * n)()
    _glGetIntegerv(pname, arr)
    return arr[0] if n == 1 else list(arr)


def glGetFloatv(pname):
    n = _INT_PNAMES_N.get(pname, 1)
    arr = (_c.c_float * n)()
    _glGetFloatv(pname, arr)
    return [arr[0]] if n == 1 else list(arr)


def _fv(fn, location, count, value):
    a = np.ascontiguousarray(value, dtype=np.float32)
    fn(location, count, a.ctypes.data_as(_p(_c.c_float)))


def glUniform2fv(location, count, value):
    _fv(_glUniform2fv, location, count, value)


def glUniform3fv(location, count, value):
    _fv(_glUniform3fv, location, count, value)


def glUniform4fv(location, count, value):
    _fv(_glUniform4fv, location, count, value)


def _mfv(fn, location, count, transpose, value):
    a = np.ascontiguousarray(value, dtype=np.float32)
    fn(
        location, count, 1 if transpose else 0,
        a.ctypes.data_as(_p(_c.c_float)),
    )


def glUniformMatrix3fv(location, count, transpose, value):
    _mfv(_glUniformMatrix3fv, location, count, transpose, value)


def glUniformMatrix4fv(location, count, transpose, value):
    _mfv(_glUniformMatrix4fv, location, count, transpose, value)


def glGetUniformLocation(program, name):
    if isinstance(name, str):
        name = name.encode()
    return _glGetUniformLocation(int(program), name)


def glReadPixels(x, y, width, height, fmt, type_, out=None):
    if fmt != GL_RGBA or type_ != GL_UNSIGNED_BYTE:
        raise GLError("glReadPixels shim supports RGBA/UNSIGNED_BYTE")
    a = np.empty((height, width, 4), np.uint8)
    _glReadPixels(
        x, y, width, height, fmt, type_,
        a.ctypes.data_as(_c.c_void_p),
    )
    return a


def glDepthMask(flag):
    _glDepthMask(1 if flag else 0)


# thin passthroughs
glGetError = _glGetError
glEnable = _glEnable
glDisable = _glDisable
glBlendFunc = _glBlendFunc
glDepthFunc = _glDepthFunc
glClearColor = _glClearColor
glClear = _glClear
glViewport = _glViewport
glLineWidth = _glLineWidth
glPixelStorei = _glPixelStorei
glBindBuffer = _glBindBuffer
glBindVertexArray = _glBindVertexArray
glEnableVertexAttribArray = _glEnableVertexAttribArray
glDrawArrays = _glDrawArrays
glBindTexture = _glBindTexture
glActiveTexture = _glActiveTexture
glTexParameteri = _glTexParameteri
glUseProgram = lambda p: _glUseProgram(int(p))  # noqa: E731
glUniform1i = _glUniform1i
glUniform1f = _glUniform1f
glBindFramebuffer = _glBindFramebuffer
glBindRenderbuffer = _glBindRenderbuffer
glRenderbufferStorage = _glRenderbufferStorage
glFramebufferRenderbuffer = _glFramebufferRenderbuffer
glCheckFramebufferStatus = _glCheckFramebufferStatus
glFinish = _glFinish

# internals used by shaders.py
_shader_fns = dict(
    create=_glCreateShader,
    delete=_glDeleteShader,
    source=_glShaderSource,
    compile=_glCompileShader,
    getiv=_glGetShaderiv,
    infolog=_glGetShaderInfoLog,
    pcreate=_glCreateProgram,
    pdelete=_glDeleteProgram,
    attach=_glAttachShader,
    link=_glLinkProgram,
    validate=_glValidateProgram,
    pgetiv=_glGetProgramiv,
    pinfolog=_glGetProgramInfoLog,
)

from . import shaders  # noqa: E402,F401
