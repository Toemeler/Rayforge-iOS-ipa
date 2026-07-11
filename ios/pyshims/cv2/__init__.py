"""iOS cv2 shim for Rayforge.

opencv-python has no iOS build. This module implements the *exact*
subset of cv2 that Rayforge's camera pipeline uses — MJPEG-over-HTTP
capture, channel conversions, homography, perspective warp, temporal
denoise — in pure Python + numpy, with JPEG decoding delegated to
GdkPixbuf (always present in this app's GTK stack; PIL fallback for
desktop tests). Everything NOT implemented keeps the previous stub
behavior: attribute access raises a clear feature error, so no OpenCV
behavior is ever silently faked.
"""

import threading
import time
import urllib.request

import numpy as np

__version__ = "0.1.0+ios.shim"


class error(Exception):
    """cv2.error stand-in."""


_CV2Unavailable = error  # old stub name, kept for any external refs

_MSG = (
    "This OpenCV (cv2) function is not available in the iOS build of "
    "Rayforge. The camera live view/alignment path is supported; "
    "advanced CV features (tracing, ChArUco calibration, fisheye "
    "undistort) are not supported on iOS yet."
)

# ---------------------------------------------------------------------
# Constants (values match real OpenCV)
# ---------------------------------------------------------------------
CAP_ANY = 0
CAP_V4L2 = 200
CAP_DSHOW = 700
CAP_MSMF = 1400

CAP_PROP_FRAME_WIDTH = 3
CAP_PROP_FRAME_HEIGHT = 4
CAP_PROP_FOURCC = 6
CAP_PROP_BRIGHTNESS = 10
CAP_PROP_CONTRAST = 11
CAP_PROP_BUFFERSIZE = 38
CAP_PROP_AUTO_WB = 44
CAP_PROP_WB_TEMPERATURE = 45

COLOR_BGR2BGRA = 0
COLOR_BGRA2BGR = 1
COLOR_BGR2RGB = 4  # == COLOR_RGB2BGR
COLOR_RGB2BGR = 4
COLOR_BGR2GRAY = 6
COLOR_RGB2RGBA = 0  # same op as BGR2BGRA (append alpha)
COLOR_BGRA2GRAY = 10
BORDER_CONSTANT = 0

INTER_NEAREST = 0
INTER_LINEAR = 1
INTER_CUBIC = 2
INTER_AREA = 3


def VideoWriter_fourcc(*chars):
    v = 0
    for i, c in enumerate(chars):
        v |= (ord(c) & 0xFF) << (8 * i)
    return v


# ---------------------------------------------------------------------
# JPEG decode: GdkPixbuf on iOS, PIL fallback for desktop tests
# ---------------------------------------------------------------------
def _decode_jpeg_gdk(data: bytes):
    from gi.repository import GdkPixbuf

    loader = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
    try:
        loader.write(data)
    finally:
        loader.close()
    pb = loader.get_pixbuf()
    if pb is None:
        raise error("JPEG decode failed")
    w, h = pb.get_width(), pb.get_height()
    stride = pb.get_rowstride()
    nch = pb.get_n_channels()
    buf = np.frombuffer(pb.get_pixels(), dtype=np.uint8)
    buf = buf.reshape(h, stride)[:, : w * nch].reshape(h, w, nch)
    rgb = buf[:, :, :3]
    return rgb[:, :, ::-1].copy()  # -> BGR


def _decode_jpeg_pil(data: bytes):
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.asarray(img)[:, :, ::-1].copy()  # -> BGR


def _decode_jpeg(data: bytes):
    try:
        return _decode_jpeg_gdk(data)
    except ImportError:
        return _decode_jpeg_pil(data)


# ---------------------------------------------------------------------
# VideoCapture: MJPEG over HTTP (multipart/x-mixed-replace)
# ---------------------------------------------------------------------
class VideoCapture:
    """Supports http(s) MJPEG stream URLs. Local device indices are
    not supported on iOS (no cv2 camera backends)."""

    _CONNECT_TIMEOUT = 4.0
    _FIRST_FRAME_TIMEOUT = 5.0
    _READ_TIMEOUT = 3.0

    def __init__(self, device, backend=None):
        self._url = device if isinstance(device, str) else None
        self._frame = None
        self._frame_seq = 0
        self._lock = threading.Condition()
        self._running = False
        self._opened = False
        self._thread = None
        if self._url and self._url.startswith(("http://", "https://")):
            self._running = True
            self._thread = threading.Thread(
                target=self._reader, name="cv2-mjpeg", daemon=True
            )
            self._thread.start()
            # wait briefly for the connection to establish
            deadline = time.monotonic() + self._CONNECT_TIMEOUT
            with self._lock:
                while (
                    self._running
                    and not self._opened
                    and time.monotonic() < deadline
                ):
                    self._lock.wait(0.1)

    def _reader(self):
        buf = b""
        resp = None
        try:
            resp = urllib.request.urlopen(
                self._url, timeout=self._CONNECT_TIMEOUT
            )
            with self._lock:
                self._opened = True
                self._lock.notify_all()
            while self._running:
                chunk = resp.read(16384)
                if not chunk:
                    break
                buf += chunk
                # scan for complete JPEGs (SOI .. EOI)
                while True:
                    soi = buf.find(b"\xff\xd8")
                    if soi < 0:
                        buf = buf[-2:]
                        break
                    eoi = buf.find(b"\xff\xd9", soi + 2)
                    if eoi < 0:
                        buf = buf[soi:]
                        break
                    jpg, buf = buf[soi : eoi + 2], buf[eoi + 2 :]
                    try:
                        frame = _decode_jpeg(jpg)
                    except Exception:
                        continue  # torn frame; skip
                    with self._lock:
                        self._frame = frame
                        self._frame_seq += 1
                        self._lock.notify_all()
        except Exception:
            pass
        finally:
            try:
                if resp is not None:
                    resp.close()
            except Exception:
                pass
            with self._lock:
                self._running = False
                self._lock.notify_all()

    def isOpened(self):
        return self._opened and self._running

    def read(self):
        deadline = time.monotonic() + self._READ_TIMEOUT
        seq = self._frame_seq
        with self._lock:
            while self._running and time.monotonic() < deadline:
                if self._frame is not None and self._frame_seq != seq:
                    return True, self._frame.copy()
                self._lock.wait(0.1)
            # stream alive but no *new* frame: return latest if any
            if self._frame is not None:
                return True, self._frame.copy()
        return False, None

    def set(self, prop, value):  # network stream: settings are no-ops
        return False

    def get(self, prop):
        with self._lock:
            if self._frame is not None:
                if prop == CAP_PROP_FRAME_WIDTH:
                    return float(self._frame.shape[1])
                if prop == CAP_PROP_FRAME_HEIGHT:
                    return float(self._frame.shape[0])
        return 0.0

    def release(self):
        self._running = False
        with self._lock:
            self._lock.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def __bool__(self):
        return True


# ---------------------------------------------------------------------
# numpy implementations of the used image ops
# ---------------------------------------------------------------------
def cvtColor(src, code):
    a = np.asarray(src)
    if code in (COLOR_BGR2RGB,):  # == RGB2BGR, symmetric swap
        return a[:, :, ::-1].copy()
    if code == COLOR_BGR2BGRA:
        alpha = np.full(a.shape[:2] + (1,), 255, dtype=a.dtype)
        return np.concatenate([a, alpha], axis=2)
    if code == COLOR_BGRA2BGR:
        return a[:, :, :3].copy()
    if code == COLOR_BGRA2GRAY:
        a = np.asarray(src).astype(np.float64)
        gray = 0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2]
        return np.clip(np.rint(gray), 0, 255).astype(np.uint8)
    if code == COLOR_BGR2GRAY:
        w = np.array([0.114, 0.587, 0.299])  # BGR weights
        return (a[:, :, :3].astype(np.float32) @ w).astype(a.dtype)
    raise error(f"cvtColor code {code} not supported in iOS shim")


def findHomography(src_pts, dst_pts, *args, **kwargs):
    """Direct linear transform, least squares (no RANSAC — Rayforge
    passes exactly the 4 alignment correspondences)."""
    s = np.asarray(src_pts, dtype=np.float64).reshape(-1, 2)
    d = np.asarray(dst_pts, dtype=np.float64).reshape(-1, 2)
    n = s.shape[0]
    if n < 4 or d.shape[0] != n:
        raise error("findHomography needs >= 4 point pairs")
    A = []
    for (x, y), (u, v) in zip(s, d):
        A.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        A.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    A = np.asarray(A)
    _, _, Vt = np.linalg.svd(A)
    H = Vt[-1].reshape(3, 3)
    if abs(H[2, 2]) < 1e-12:
        raise error("degenerate homography")
    H = H / H[2, 2]
    mask = np.ones((n, 1), dtype=np.uint8)
    return H, mask


def warpPerspective(src, M, dsize):
    """dst(x,y) = src(Minv @ (x,y,1)), bilinear, zeros outside."""
    a = np.asarray(src)
    w_out, h_out = int(dsize[0]), int(dsize[1])
    Minv = np.linalg.inv(np.asarray(M, dtype=np.float64))
    xs, ys = np.meshgrid(np.arange(w_out), np.arange(h_out))
    ones = np.ones_like(xs)
    pts = np.stack([xs, ys, ones], axis=0).reshape(3, -1)
    sp = Minv @ pts
    with np.errstate(divide="ignore", invalid="ignore"):
        sx = sp[0] / sp[2]
        sy = sp[1] / sp[2]
    h_in, w_in = a.shape[:2]
    valid = (
        np.isfinite(sx) & np.isfinite(sy)
        & (sx >= 0) & (sx <= w_in - 1)
        & (sy >= 0) & (sy <= h_in - 1)
    )
    sx = np.clip(np.nan_to_num(sx), 0, w_in - 1)
    sy = np.clip(np.nan_to_num(sy), 0, h_in - 1)
    x0 = np.floor(sx).astype(np.int64)
    y0 = np.floor(sy).astype(np.int64)
    x1 = np.minimum(x0 + 1, w_in - 1)
    y1 = np.minimum(y0 + 1, h_in - 1)
    fx = (sx - x0).astype(np.float32)
    fy = (sy - y0).astype(np.float32)
    if a.ndim == 2:
        a3 = a[:, :, None]
    else:
        a3 = a
    fa = a3.astype(np.float32)
    fx = fx[:, None]
    fy = fy[:, None]
    top = fa[y0, x0] * (1 - fx) + fa[y0, x1] * fx
    bot = fa[y1, x0] * (1 - fx) + fa[y1, x1] * fx
    out = top * (1 - fy) + bot * fy
    out[~valid] = 0
    out = out.reshape(h_out, w_out, a3.shape[2])
    if a.ndim == 2:
        out = out[:, :, 0]
    return out.astype(a.dtype)


def resize(src, dsize, fx=0, fy=0, interpolation=INTER_LINEAR):
    """Bilinear resize (used for camera display scaling). dsize is
    (width, height) like cv2. INTER_AREA is approximated bilinearly."""
    a = np.asarray(src)
    h_in, w_in = a.shape[:2]
    w_out, h_out = int(dsize[0]), int(dsize[1])
    if w_out == w_in and h_out == h_in:
        return a.copy()
    sx = (np.arange(w_out) + 0.5) * (w_in / w_out) - 0.5
    sy = (np.arange(h_out) + 0.5) * (h_in / h_out) - 0.5
    sx = np.clip(sx, 0, w_in - 1)
    sy = np.clip(sy, 0, h_in - 1)
    x0 = np.floor(sx).astype(np.int64)
    y0 = np.floor(sy).astype(np.int64)
    x1 = np.minimum(x0 + 1, w_in - 1)
    y1 = np.minimum(y0 + 1, h_in - 1)
    fxw = (sx - x0).astype(np.float32)[None, :]
    fyw = (sy - y0).astype(np.float32)[:, None]
    squeeze = a.ndim == 2
    a3 = a[:, :, None] if squeeze else a
    fa = a3.astype(np.float32)
    fxw3 = fxw[:, :, None]
    fyw3 = fyw[:, :, None]
    top = fa[y0[:, None], x0[None, :]] * (1 - fxw3) + \
        fa[y0[:, None], x1[None, :]] * fxw3
    bot = fa[y1[:, None], x0[None, :]] * (1 - fxw3) + \
        fa[y1[:, None], x1[None, :]] * fxw3
    out = top * (1 - fyw3) + bot * fyw3
    if squeeze:
        out = out[:, :, 0]
    if np.issubdtype(a.dtype, np.integer):
        out = np.rint(out)
    return out.astype(a.dtype)


def accumulateWeighted(src, dst, alpha):
    """dst = (1-alpha)*dst + alpha*src, in place (dst is float)."""
    np.multiply(dst, 1.0 - alpha, out=dst)
    dst += np.asarray(src).astype(dst.dtype) * alpha
    return dst


def undistort(src, cameraMatrix, distCoeffs, *a, **kw):
    raise error(_MSG + " (cv2.undistort)")


# ---------------------------------------------------------------------
# Fallback: unimplemented names raise clearly (previous stub behavior)
# ---------------------------------------------------------------------
_placeholder_cache: dict = {}


class _RaisingMeta(type):
    def __getattr__(cls, name):
        raise error(f"{_MSG} (attribute: cv2.{cls.__name__}.{name})")

    def __call__(cls, *a, **kw):
        raise error(f"{_MSG} (instantiating cv2.{cls.__name__})")


def copyMakeBorder(src, top, bottom, left, right, borderType,
                   value=None):
    """Constant-border padding (the only mode rayforge uses)."""
    if borderType != BORDER_CONSTANT:
        raise Error(f"copyMakeBorder borderType {borderType} unsupported")
    a = np.asarray(src)
    if value is None:
        fill = 0
    elif np.isscalar(value):
        fill = value
    else:
        fill = value[0] if len(value) else 0
    if a.ndim == 2:
        out = np.full(
            (a.shape[0] + top + bottom, a.shape[1] + left + right),
            fill, dtype=a.dtype,
        )
    else:
        out = np.full(
            (a.shape[0] + top + bottom, a.shape[1] + left + right,
             a.shape[2]),
            fill, dtype=a.dtype,
        )
    out[top:top + a.shape[0], left:left + a.shape[1]] = a
    return out


def imencode(ext, img, params=None):
    """BMP encoding only (what rayforge's tracing path uses).

    Matches OpenCV semantics: 3-channel input is BGR; BMP stores BGR
    bottom-up, so bytes are written verbatim. Grayscale is expanded.
    """
    import struct as _st
    if str(ext).lower() not in (".bmp", "bmp"):
        raise Error(f"imencode {ext} unsupported in iOS build")
    a = np.asarray(img)
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8)
    if a.ndim == 2:
        a = np.repeat(a[:, :, None], 3, axis=2)
    if a.shape[2] == 4:
        a = a[:, :, :3]
    h, w = a.shape[:2]
    row_bytes = w * 3
    pad = (4 - row_bytes % 4) % 4
    stride = row_bytes + pad
    img_size = stride * h
    header = _st.pack(
        "<2sIHHI", b"BM", 14 + 40 + img_size, 0, 0, 14 + 40
    )
    dib = _st.pack(
        "<IiiHHIIiiII", 40, w, h, 1, 24, 0, img_size, 2835, 2835, 0, 0
    )
    rows = bytearray()
    zeros = b"\x00" * pad
    for r in range(h - 1, -1, -1):  # bottom-up
        rows += a[r].tobytes()
        rows += zeros
    buf = header + dib + bytes(rows)
    return True, np.frombuffer(buf, dtype=np.uint8)


def _is_class_like(name: str) -> bool:
    return name[:1].isupper() and not name.isupper()


def __getattr__(name):
    if _is_class_like(name):
        cls = _placeholder_cache.get(name)
        if cls is None:
            cls = _RaisingMeta(name, (), {"__module__": __name__})
            _placeholder_cache[name] = cls
        return cls
    raise error(f"{_MSG} (attribute: cv2.{name})")
