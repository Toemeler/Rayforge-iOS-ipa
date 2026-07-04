"""iOS shim for the tiny slice of SciPy that Rayforge actually uses.

SciPy has no iOS build (Fortran/BLAS toolchain), but Rayforge's core
only calls two functions:

  * scipy.ndimage.binary_dilation(mask, iterations=N)
      — default 3x3 cross structuring element (connectivity 1)
  * scipy.signal.fftconvolve(a, b, mode="valid")
      — 2-D float convolution

Both are implemented here on top of numpy with matching semantics for
exactly the argument patterns Rayforge uses (verified numerically
against SciPy 1.17.1 in CI of the port). Anything else raises
ImportError-style AttributeErrors naturally, so unexpected new SciPy
usage fails loudly instead of silently misbehaving.

This package shadows `scipy` on sys.path inside the iOS bundle only.
"""

__version__ = "1.17.1+rayforge.ios.shim"
