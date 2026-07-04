"""scipy.linalg shim — null_space via numpy SVD (exact match to scipy)."""
import numpy as np


def null_space(A, rcond=None):
    A = np.atleast_2d(np.asarray(A, dtype=float))
    u, s, vh = np.linalg.svd(A, full_matrices=True)
    M, N = A.shape
    if rcond is None:
        rcond = np.finfo(s.dtype).eps * max(M, N)
    tol = np.amax(s) * rcond if s.size else 0.0
    num = np.sum(s > tol, dtype=int)
    Q = vh[num:, :].T.conj()
    return Q
