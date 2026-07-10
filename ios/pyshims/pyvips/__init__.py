"""iOS pyvips shim: a numpy-backed mini Image implementing exactly the
operations Rayforge's raster pipeline uses (DXF renderer, normalize,
cairo conversion, crop/resize). Unknown operations raise Error, so
paths with their own fallbacks (e.g. SVG via svgload_buffer) behave
exactly as before.
"""
import numpy as _np


class Error(RuntimeError):
    pass


_PyvipsUnavailable = Error  # legacy name

_MSG = (
    "pyvips/libvips operation not supported in the iOS build of "
    "Rayforge"
)


class _ImageMeta(type):
    def __getattr__(cls, name):
        # unknown class-level ops (svgload_buffer, black, ...) raise
        # Error exactly like the previous stub, so existing fallback
        # paths (P14 SVG) keep triggering identically.
        raise Error(_MSG + f" (Image.{name})")


class Image(metaclass=_ImageMeta):
    def __init__(self, arr):
        a = _np.asarray(arr)
        if a.ndim == 2:
            a = a[:, :, None]
        self._a = a

    # --- constructors -------------------------------------------------
    @staticmethod
    def new_from_memory(data, width, height, bands, format):
        if format != "uchar":
            raise Error(_MSG + f" (new_from_memory format {format})")
        a = _np.frombuffer(bytes(data), dtype=_np.uint8)
        a = a.reshape(int(height), int(width), int(bands)).copy()
        return Image(a)

    # --- properties ----------------------------------------------------
    @property
    def width(self):
        return int(self._a.shape[1])

    @property
    def height(self):
        return int(self._a.shape[0])

    @property
    def bands(self):
        return int(self._a.shape[2])

    @property
    def format(self):
        return "uchar" if self._a.dtype == _np.uint8 else str(self._a.dtype)

    @property
    def interpretation(self):
        return "srgb"

    # --- band ops --------------------------------------------------
    def __getitem__(self, i):
        if isinstance(i, slice):
            return Image(self._a[:, :, i].copy())
        return Image(self._a[:, :, int(i)].copy())

    def bandjoin(self, others):
        if isinstance(others, Image):
            others = [others]
        parts = [self._a] + [
            (o._a if isinstance(o, Image) else
             _np.full(self._a.shape[:2] + (1,), int(o), _np.uint8))
            for o in others
        ]
        return Image(_np.concatenate(parts, axis=2))

    def hasalpha(self):
        return self.bands in (2, 4)

    def addalpha(self):
        alpha = _np.full(self._a.shape[:2] + (1,), 255, self._a.dtype)
        return Image(_np.concatenate([self._a, alpha], axis=2))

    def colourspace(self, space):
        if space != "srgb":
            raise Error(_MSG + f" (colourspace {space})")
        if self.bands == 1:
            return Image(_np.repeat(self._a, 3, axis=2))
        return self

    def cast(self, fmt):
        if fmt != "uchar":
            raise Error(_MSG + f" (cast {fmt})")
        a = self._a
        if a.dtype != _np.uint8:
            a = _np.clip(a, 0, 255).astype(_np.uint8)
        return Image(a)

    # --- geometry ops ---------------------------------------------
    def extract_area(self, left, top, w, h):
        l, t, w, h = int(left), int(top), int(w), int(h)
        return Image(self._a[t:t + h, l:l + w].copy())

    crop = extract_area

    def resize(self, hscale, vscale=None, **kw):
        vs = hscale if vscale is None else vscale
        h, w = self._a.shape[:2]
        nw = max(1, int(round(w * float(hscale))))
        nh = max(1, int(round(h * float(vs))))
        yi = _np.minimum(
            (_np.arange(nh) / float(vs)).astype(_np.int64), h - 1
        )
        xi = _np.minimum(
            (_np.arange(nw) / float(hscale)).astype(_np.int64), w - 1
        )
        return Image(self._a[yi[:, None], xi[None, :]].copy())

    def thumbnail_image(self, width, height=None, **kw):
        s = float(width) / self.width
        return self.resize(s)

    def embed(self, x, y, w, h, extend="black", background=None):
        out = _np.zeros((int(h), int(w), self.bands), self._a.dtype)
        if background is not None:
            bg = _np.asarray(background, self._a.dtype)
            out[:, :] = bg[: self.bands]
        x, y = int(x), int(y)
        out[y:y + self.height, x:x + self.width] = self._a
        return Image(out)

    def flatten(self, background=None):
        if self.bands != 4:
            return self
        bg = _np.asarray(background or [255, 255, 255], _np.float32)
        a = self._a.astype(_np.float32)
        alpha = a[:, :, 3:4] / 255.0
        rgb = a[:, :, :3] * alpha + bg[None, None, :] * (1 - alpha)
        return Image(rgb.astype(_np.uint8))

    def write_to_memory(self):
        return _np.ascontiguousarray(self._a).tobytes()

    def __getattr__(self, name):
        raise Error(_MSG + f" (Image.{name})")


def __getattr__(name):
    raise Error(_MSG + f" (pyvips.{name})")
