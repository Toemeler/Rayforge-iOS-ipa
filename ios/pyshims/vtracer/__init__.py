"""iOS stub for vtracer (Phase 1).

vtracer is only consumed by Rayforge's raster tracing pipeline
(image/tracing.py), which is already disabled in Phase 1 via the cv2
stub — building the Rust extension would add nothing usable yet, and
the released vtracer pins a pre-iOS pyo3 that fails to link for iOS
targets. Real vtracer + OpenCV land together in Phase 2.

Import succeeds; any use raises a clear feature error.
"""

__version__ = "0.0.0+ios.stub"


class _VtracerUnavailable(RuntimeError):
    pass


def __getattr__(name):
    raise _VtracerUnavailable(
        "vtracer is not available in this iOS build (raster tracing is "
        f"disabled in Phase 1). Attribute: vtracer.{name}"
    )
