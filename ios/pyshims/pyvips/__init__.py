"""iOS stub for pyvips (Phase 1).

libvips is a large C stack with no iOS build yet; Rayforge imports
pyvips at module level in core/source_asset.py and image/util/vips.py
and uses `pyvips.Image` in runtime-evaluated type annotations, so the
stub must provide a real Image class (annotation evaluation would
otherwise crash at class-definition time). Any actual *use* — class
methods like Image.pngload_buffer/new_from_buffer or attribute access —
raises a clear feature error: image import/preview paths that need vips
are disabled in Phase 1.
"""

__version__ = "0.0.0+ios.stub"


class _PyvipsUnavailable(RuntimeError):
    pass


_MSG = (
    "pyvips/libvips is not available in this iOS build of Rayforge; "
    "the image operation that requested it is not supported yet."
)


class _RaisingMeta(type):
    def __getattr__(cls, name):
        raise _PyvipsUnavailable(f"{_MSG} (pyvips.Image.{name})")


class Image(metaclass=_RaisingMeta):
    """Type-annotation-safe placeholder; any use raises."""

    def __init__(self, *a, **kw):
        raise _PyvipsUnavailable(_MSG)


class Error(_PyvipsUnavailable):
    pass


def __getattr__(name):
    raise _PyvipsUnavailable(f"{_MSG} (pyvips.{name})")
