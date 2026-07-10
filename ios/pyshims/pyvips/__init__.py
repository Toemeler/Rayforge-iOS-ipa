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


def _png_unfilter(raw, height, stride, bpp):
    """Undo PNG per-row filtering. raw = decompressed IDAT bytes."""
    out = _np.empty(height * stride, _np.uint8)
    pos = 0
    prev = _np.zeros(stride, _np.int32)
    for r in range(height):
        ftype = raw[pos]
        pos += 1
        row = _np.frombuffer(
            raw, _np.uint8, stride, pos
        ).astype(_np.int32)
        pos += stride
        if ftype == 0:
            cur = row
        elif ftype == 1:  # Sub
            cur = row.copy()
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 0xFF
        elif ftype == 2:  # Up
            cur = (row + prev) & 0xFF
        elif ftype == 3:  # Average
            cur = row.copy()
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            cur = row.copy()
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (
                    b if pb <= pc else c
                )
                cur[i] = (cur[i] + pred) & 0xFF
        else:
            raise Error(_MSG + f" (PNG filter {ftype})")
        out[r * stride:(r + 1) * stride] = cur.astype(_np.uint8)
        prev = cur
    return out


def _png_decode(data):
    import struct as _st
    import zlib as _zl
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise Error(_MSG + " (not a PNG)")
    pos = 8
    width = height = None
    bitdepth = ctype = None
    idat = []
    plte = None
    trns = None
    while pos + 8 <= len(data):
        (ln,) = _st.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            (width, height, bitdepth, ctype,
             _comp, _filt, interlace) = _st.unpack(">IIBBBBB", body)
            if bitdepth != 8 or interlace != 0:
                raise Error(
                    _MSG + f" (PNG bitdepth={bitdepth}"
                    f" interlace={interlace})"
                )
        elif tag == b"PLTE":
            plte = _np.frombuffer(body, _np.uint8).reshape(-1, 3)
        elif tag == b"tRNS":
            trns = _np.frombuffer(body, _np.uint8)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
    if width is None or not idat:
        raise Error(_MSG + " (malformed PNG)")
    nch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if nch is None:
        raise Error(_MSG + f" (PNG color type {ctype})")
    raw = _zl.decompress(b"".join(idat))
    stride = width * nch
    px = _png_unfilter(raw, height, stride, nch)
    a = px.reshape(height, width, nch)
    if ctype == 3:  # palette
        if plte is None:
            raise Error(_MSG + " (PNG palette missing)")
        idx = a[:, :, 0]
        rgb = plte[idx]
        if trns is not None:
            alpha = _np.full(idx.shape, 255, _np.uint8)
            n = min(len(trns), plte.shape[0])
            alpha = _np.where(
                idx < n,
                trns[_np.minimum(idx, n - 1)],
                alpha,
            ).astype(_np.uint8)
            a = _np.concatenate([rgb, alpha[:, :, None]], axis=2)
        else:
            a = rgb
    return _np.ascontiguousarray(a)


def _png_encode(a):
    import struct as _st
    import zlib as _zl
    h, w, bands = a.shape
    ctype = {1: 0, 2: 4, 3: 2, 4: 6}[bands]
    rows = b"".join(
        b"\x00" + a[r].tobytes() for r in range(h)
    )

    def chunk(tag, body):
        c = _st.pack(">I", len(body)) + tag + body
        return c + _st.pack(">I", _zl.crc32(tag + body) & 0xFFFFFFFF)

    ihdr = _st.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", _zl.compress(rows, 6))
        + chunk(b"IEND", b"")
    )


_SRGB_TO_LINEAR = None


def _srgb_decode_lut():
    global _SRGB_TO_LINEAR
    if _SRGB_TO_LINEAR is None:
        v = _np.arange(256, dtype=_np.float32) / 255.0
        lin = _np.where(
            v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4
        )
        _SRGB_TO_LINEAR = lin.astype(_np.float32)
    return _SRGB_TO_LINEAR


def _srgb_encode(lin):
    lin = _np.clip(lin, 0.0, 1.0)
    v = _np.where(
        lin <= 0.0031308,
        lin * 12.92,
        1.055 * (lin ** (1.0 / 2.4)) - 0.055,
    )
    return _np.clip(_np.rint(v * 255.0), 0, 255).astype(_np.uint8)


class Image(metaclass=_ImageMeta):
    def __init__(self, arr, linear=False):
        a = _np.asarray(arr)
        if a.ndim == 2:
            a = a[:, :, None]
        self._a = a
        self._linear = bool(linear)

    # --- constructors -------------------------------------------------
    @staticmethod
    def pngload_buffer(data, **kw):
        return Image(_png_decode(bytes(data)))

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
        if space == "scrgb":
            # sRGB uint8 -> linear float32 (alpha stays 0..1 linear)
            if self._linear:
                return self
            a = self._a
            if a.dtype != _np.uint8:
                a = _np.clip(a, 0, 255).astype(_np.uint8)
            lut = _srgb_decode_lut()
            out = lut[a]
            if self.bands in (2, 4):
                out[:, :, -1] = a[:, :, -1].astype(_np.float32) / 255.0
            return Image(out, linear=True)
        if space != "srgb":
            raise Error(_MSG + f" (colourspace {space})")
        if self._linear:
            lin = self._a
            out = _srgb_encode(lin)
            if self.bands in (2, 4):
                out[:, :, -1] = _np.clip(
                    _np.rint(lin[:, :, -1] * 255.0), 0, 255
                ).astype(_np.uint8)
            return Image(out)
        if self.bands == 1:
            return Image(_np.repeat(self._a, 3, axis=2))
        return self

    def pngsave_buffer(self, **kw):
        img = self.colourspace("srgb") if self._linear else self
        a = img._a
        if a.dtype != _np.uint8:
            a = _np.clip(a, 0, 255).astype(_np.uint8)
        return _png_encode(_np.ascontiguousarray(a))

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
        return Image(
            self._a[yi[:, None], xi[None, :]].copy(),
            linear=self._linear,
        )

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
