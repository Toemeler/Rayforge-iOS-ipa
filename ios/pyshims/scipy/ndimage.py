"""binary_dilation shim — numpy implementation matching scipy.ndimage
semantics for the default 3x3 cross structure, arbitrary iterations."""
import numpy as np


def binary_dilation(input, structure=None, iterations=1, **kwargs):
    if kwargs:
        raise NotImplementedError(
            f"scipy shim: unsupported binary_dilation kwargs {sorted(kwargs)}"
        )
    a = np.asarray(input).astype(bool)
    if a.ndim != 2:
        raise NotImplementedError("scipy shim: only 2-D masks supported")
    if structure is not None:
        structure = np.asarray(structure).astype(bool)
        if structure.shape != (3, 3) or not np.array_equal(
            structure,
            np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool),
        ):
            raise NotImplementedError(
                "scipy shim: only the default 3x3 cross structure supported"
            )
    def _dilate_once(x):
        p = np.pad(x, 1, mode="constant", constant_values=False)
        return (
            p[1:-1, 1:-1]
            | p[:-2, 1:-1]
            | p[2:, 1:-1]
            | p[1:-1, :-2]
            | p[1:-1, 2:]
        )

    out = a
    if int(iterations) < 1:
        # scipy semantics: repeat until the result no longer changes
        while True:
            nxt = _dilate_once(out)
            if np.array_equal(nxt, out):
                return nxt
            out = nxt
    for _ in range(int(iterations)):
        out = _dilate_once(out)
    return out
