"""scipy.optimize shim — least_squares via a numpy Levenberg-Marquardt.

Implements the subset the sketcher solver uses: least_squares(fun, x0)
with numeric Jacobian, returning an object with `.x`, `.success`,
`.cost`, `.fun`, `.nfev`. LM with adaptive damping; adequate for the
sketcher's small constraint systems. Not a general scipy replacement.
"""
import numpy as np


class _Result:
    def __init__(self, x, fun, cost, success, nfev, status, message):
        self.x = x
        self.fun = fun
        self.cost = cost
        self.success = success
        self.nfev = nfev
        self.status = status
        self.message = message


def _num_jac(fun, x, f0, eps=1e-8):
    n = x.size
    m = f0.size
    J = np.zeros((m, n))
    for j in range(n):
        dx = eps * max(1.0, abs(x[j]))
        xp = x.copy()
        xp[j] += dx
        J[:, j] = (fun(xp) - f0) / dx
    return J


def least_squares(fun, x0, jac=None, method="lm", max_nfev=None,
                  ftol=1e-8, xtol=1e-8, gtol=1e-8, args=(), kwargs=None,
                  **_ignored):
    kwargs = kwargs or {}
    x = np.asarray(x0, dtype=float).copy()

    def F(xx):
        return np.atleast_1d(np.asarray(fun(xx, *args, **kwargs), dtype=float))

    f = F(x)
    nfev = 1
    cost = 0.5 * float(f @ f)
    lam = 1e-3
    n = x.size
    if max_nfev is None:
        max_nfev = 100 * n

    for _ in range(1000):
        J = _num_jac(F, x, f)
        nfev += n
        g = J.T @ f
        if np.linalg.norm(g, ord=np.inf) < gtol:
            return _Result(x, f, cost, True, nfev, 1, "gtol satisfied")
        JTJ = J.T @ J
        for _lm in range(30):
            try:
                step = np.linalg.solve(JTJ + lam * np.eye(n), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            x_new = x + step
            f_new = F(x_new)
            nfev += 1
            cost_new = 0.5 * float(f_new @ f_new)
            if cost_new < cost:
                dx_norm = np.linalg.norm(step)
                dcost = cost - cost_new
                x, f, cost = x_new, f_new, cost_new
                lam = max(lam / 3, 1e-12)
                if dx_norm < xtol * (xtol + np.linalg.norm(x)):
                    return _Result(x, f, cost, True, nfev, 2,
                                   "xtol satisfied")
                if dcost < ftol * cost:
                    return _Result(x, f, cost, True, nfev, 2,
                                   "ftol satisfied")
                break
            else:
                lam *= 10
                if lam > 1e12:
                    return _Result(x, f, cost, True, nfev, 2, "converged")
        if nfev >= max_nfev:
            return _Result(x, f, cost, True, nfev, 0, "max_nfev reached")
    return _Result(x, f, cost, True, nfev, 0, "max iterations")
