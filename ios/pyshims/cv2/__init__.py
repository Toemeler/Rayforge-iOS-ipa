"""iOS stub for OpenCV (cv2).

opencv-python has no iOS build; Rayforge imports cv2 at module level in
image/tracing.py and a few camera/UI modules, so a bare ImportError
would take down whole subsystems at import time. This stub lets the
import succeed and defers the failure to the first actual *use*, which
surfaces as a clear, actionable error inside the specific feature
(raster tracing, camera calibration) instead of at startup.

Every attribute access raises; no OpenCV behavior is silently faked.
"""


class _CV2Unavailable(RuntimeError):
    pass


_MSG = (
    "OpenCV (cv2) is not available in the iOS build of Rayforge. "
    "The feature that requested it (image tracing / camera) is not "
    "supported on iOS yet."
)

__version__ = "0.0.0+ios.stub"


def __getattr__(name):
    raise _CV2Unavailable(f"{_MSG} (attribute: cv2.{name})")
