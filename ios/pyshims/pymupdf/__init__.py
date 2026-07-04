"""iOS stub for PyMuPDF (Phase 1).

Rayforge's PDF importer tries `import pymupdf` first (falling back to
`import fitz`); providing this stub as `pymupdf` satisfies that chain.
mupdf does have iOS support upstream, so a real build is a Phase-2
candidate — until then PDF import is cleanly disabled: annotation-safe
placeholder classes (Document/Page/Point/Matrix/Rect), any actual use
raises a clear feature error.
"""

__version__ = "0.0.0+ios.stub"
version = ("0.0.0", "0.0.0", "ios-stub")


class _PyMuPDFUnavailable(RuntimeError):
    pass


_MSG = (
    "PyMuPDF/mupdf is not available in this iOS build of Rayforge; "
    "PDF import is not supported yet."
)


class _RaisingMeta(type):
    def __getattr__(cls, name):
        raise _PyMuPDFUnavailable(f"{_MSG} ({cls.__name__}.{name})")


class Document(metaclass=_RaisingMeta):
    def __init__(self, *a, **kw):
        raise _PyMuPDFUnavailable(_MSG)


class Page(metaclass=_RaisingMeta):
    def __init__(self, *a, **kw):
        raise _PyMuPDFUnavailable(_MSG)


class Point(metaclass=_RaisingMeta):
    def __init__(self, *a, **kw):
        raise _PyMuPDFUnavailable(_MSG)


class Matrix(metaclass=_RaisingMeta):
    def __init__(self, *a, **kw):
        raise _PyMuPDFUnavailable(_MSG)


class Rect(metaclass=_RaisingMeta):
    def __init__(self, *a, **kw):
        raise _PyMuPDFUnavailable(_MSG)


def open(*a, **kw):  # noqa: A001 — mirrors pymupdf.open
    raise _PyMuPDFUnavailable(_MSG)


def __getattr__(name):
    raise _PyMuPDFUnavailable(f"{_MSG} (pymupdf.{name})")
