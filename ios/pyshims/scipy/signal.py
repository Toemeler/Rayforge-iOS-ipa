"""fftconvolve shim — numpy.fft implementation, 2-D, modes full/valid/same."""
import numpy as np


def fftconvolve(in1, in2, mode="full", axes=None):
    if axes is not None:
        raise NotImplementedError("scipy shim: axes not supported")
    a = np.asarray(in1)
    b = np.asarray(in2)
    if a.ndim != 2 or b.ndim != 2:
        raise NotImplementedError("scipy shim: only 2-D inputs supported")
    if mode not in ("full", "valid", "same"):
        raise ValueError(f"invalid mode {mode!r}")

    full_shape = (a.shape[0] + b.shape[0] - 1, a.shape[1] + b.shape[1] - 1)
    fa = np.fft.rfft2(a, full_shape)
    fb = np.fft.rfft2(b, full_shape)
    full = np.fft.irfft2(fa * fb, full_shape)

    if mode == "full":
        out = full
    elif mode == "valid":
        # scipy requires one input to be at least as large as the other
        # in every dimension for 'valid'
        oh = a.shape[0] - b.shape[0] + 1
        ow = a.shape[1] - b.shape[1] + 1
        if oh < 1 or ow < 1:
            oh = b.shape[0] - a.shape[0] + 1
            ow = b.shape[1] - a.shape[1] + 1
            if oh < 1 or ow < 1:
                raise ValueError(
                    "valid mode: one input must be at least as large as the "
                    "other in every dimension"
                )
        sy = (full_shape[0] - oh) // 2
        sx = (full_shape[1] - ow) // 2
        out = full[sy : sy + oh, sx : sx + ow]
    else:  # same
        sy = (full_shape[0] - a.shape[0]) // 2
        sx = (full_shape[1] - a.shape[1]) // 2
        out = full[sy : sy + a.shape[0], sx : sx + a.shape[1]]

    if np.issubdtype(a.dtype, np.floating) and a.dtype == np.float32 \
            and b.dtype == np.float32:
        out = out.astype(np.float32)
    return out
