"""iOS stub for OpenCV (cv2).

opencv-python has no iOS build; Rayforge imports cv2 at module level
AND references cv2 classes (e.g. cv2.VideoCapture) in runtime-evaluated
type annotations, so the stub must be annotation-safe: CamelCase
attribute access yields a cached raising placeholder CLASS (safe to use
as an annotation; instantiating or touching it raises), while
functions/constants raise immediately on access. No OpenCV behavior is
silently faked — every actual use surfaces as a clear feature error.
"""

__version__ = "0.0.0+ios.stub"


class _CV2Unavailable(RuntimeError):
    pass


_MSG = (
    "OpenCV (cv2) is not available in the iOS build of Rayforge. "
    "The feature that requested it (image tracing / camera) is not "
    "supported on iOS yet."
)

_placeholder_cache: dict = {}


class _RaisingMeta(type):
    def __getattr__(cls, name):
        raise _CV2Unavailable(f"{_MSG} (attribute: cv2.{cls.__name__}.{name})")

    def __call__(cls, *a, **kw):
        raise _CV2Unavailable(f"{_MSG} (instantiating cv2.{cls.__name__})")


def _is_class_like(name: str) -> bool:
    # CamelCase (VideoCapture) yes; ALL_CAPS constants (CAP_PROP_*) no;
    # lowercase functions (imread) no.
    return name[:1].isupper() and not name.isupper()


def __getattr__(name):
    if _is_class_like(name):
        cls = _placeholder_cache.get(name)
        if cls is None:
            cls = _RaisingMeta(name, (), {"__module__": __name__})
            _placeholder_cache[name] = cls
        return cls
    raise _CV2Unavailable(f"{_MSG} (attribute: cv2.{name})")
