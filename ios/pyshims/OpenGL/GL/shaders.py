"""PyOpenGL's OpenGL.GL.shaders subset used by rayforge."""

import ctypes

from . import (
    GL_COMPILE_STATUS,
    GL_INFO_LOG_LENGTH,
    GL_LINK_STATUS,
    GLError,
    _shader_fns as F,
)


class ShaderCompilationError(GLError):
    pass


class ShaderValidationError(GLError):
    pass


def _info_log(obj, getiv, infolog):
    n = ctypes.c_int()
    getiv(obj, GL_INFO_LOG_LENGTH, ctypes.byref(n))
    if n.value <= 1:
        return ""
    buf = ctypes.create_string_buffer(n.value)
    infolog(obj, n.value, None, buf)
    return buf.value.decode(errors="replace")


def compileShader(source, shader_type):
    if isinstance(source, (list, tuple)):
        source = "".join(source)
    shader = F["create"](shader_type)
    src = source.encode()
    arr = (ctypes.c_char_p * 1)(src)
    length = (ctypes.c_int * 1)(len(src))
    F["source"](shader, 1, arr, length)
    F["compile"](shader)
    ok = ctypes.c_int()
    F["getiv"](shader, GL_COMPILE_STATUS, ctypes.byref(ok))
    if not ok.value:
        log = _info_log(shader, F["getiv"], F["infolog"])
        F["delete"](shader)
        raise ShaderCompilationError(
            f"Shader compile failure: {log}\n---\n{source[:400]}"
        )
    return shader


def compileProgram(*shaders, validate=False):
    program = F["pcreate"]()
    for s in shaders:
        F["attach"](program, s)
    F["link"](program)
    ok = ctypes.c_int()
    F["pgetiv"](program, GL_LINK_STATUS, ctypes.byref(ok))
    if not ok.value:
        log = _info_log(program, F["pgetiv"], F["pinfolog"])
        F["pdelete"](program)
        raise ShaderValidationError(f"Program link failure: {log}")
    for s in shaders:
        F["delete"](s)
    return program
