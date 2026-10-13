"""HMM gaussiano univariante en numpy puro (Baum-Welch + filtrado causal).

Se usa para estimar la probabilidad de régimen de alta volatilidad. **Sólo** el
filtrado hacia delante (``filter``/``filter_step``) se usa en tiempo real: el
suavizado (forward-backward) usaría información futura y está reservado al ajuste.
"""

from __future__ import annotations

import numpy as np


class GaussianHMM:
    def __init__(
        self,
        n_states: int = 2,
        n_iter: int = 100,
        tol: float = 1e-5,
        min_var: float = 1e-8,
        sticky: float = 0.95,
    ) -> None:
        if n_states < 2:
            raise ValueError("n_states >= 2")
        self.k = n_states
        self.n_iter = n_iter
        self.tol = tol
        self.min_var = min_var
        self.sticky = sticky
        self.means: np.ndarray | None = None
        self.vars: np.ndarray | None = None
        self.trans: np.ndarray | None = None
        self.start: np.ndarray | None = None

    @property
    def fitted(self) -> bool:
        return self.means is not None

    def _emis(self, x: np.ndarray) -> np.ndarray:
        assert self.means is not None and self.vars is not None
        d = x[:, None] - self.means[None, :]
        b = np.exp(-0.5 * d * d / self.vars) / np.sqrt(2 * np.pi * self.vars)
        return np.maximum(b, 1e-300)

    def fit(self, x: np.ndarray) -> "GaussianHMM":
        x = np.asarray(x, dtype=float)
        x = x[np.isfinite(x)]
        if len(x) < 10 * self.k:
            raise ValueError("Muy pocas observaciones para ajustar el HMM")
        k = self.k
        qs = np.quantile(x, np.linspace(0.15, 0.85, k))
        self.means = qs.astype(float)
        self.vars = np.full(k, max(np.var(x), self.min_var))
        self.trans = np.full((k, k), (1 - self.sticky) / (k - 1))
        np.fill_diagonal(self.trans, self.sticky)
        self.start = np.full(k, 1.0 / k)
        prev_ll = -np.inf
        t_len = len(x)
        for _ in range(self.n_iter):
            b = self._emis(x)
            alpha = np.empty((t_len, k))
            c = np.empty(t_len)
            alpha[0] = self.start * b[0]
            c[0] = alpha[0].sum()
            alpha[0] /= c[0]
            for t in range(1, t_len):
                alpha[t] = (alpha[t - 1] @ self.trans) * b[t]
                c[t] = alpha[t].sum()
                alpha[t] /= c[t]
            beta = np.empty((t_len, k))
            beta[-1] = 1.0
            for t in range(t_len - 2, -1, -1):
                beta[t] = (self.trans @ (b[t + 1] * beta[t + 1])) / c[t + 1]
            gamma = alpha * beta
            gamma /= gamma.sum(axis=1, keepdims=True)
            xi = (
                alpha[:-1, :, None]
                * self.trans[None, :, :]
                * (b[1:] * beta[1:])[:, None, :]
                / c[1:, None, None]
            )
            self.start = gamma[0]
            self.trans = xi.sum(axis=0) / gamma[:-1].sum(axis=0)[:, None]
            self.trans /= self.trans.sum(axis=1, keepdims=True)
            w = gamma.sum(axis=0)
            self.means = (gamma * x[:, None]).sum(axis=0) / w
            self.vars = np.maximum(
                (gamma * (x[:, None] - self.means[None, :]) ** 2).sum(axis=0) / w, self.min_var
            )
            ll = float(np.log(c).sum())
            if abs(ll - prev_ll) < self.tol * max(1.0, abs(ll)):
                break
            prev_ll = ll
        order = np.argsort(self.means)  # estado 0 = media más baja
        self.means, self.vars = self.means[order], self.vars[order]
        self.trans = self.trans[np.ix_(order, order)]
        self.start = self.start[order]
        return self

    def filter_step(self, prev: np.ndarray | None, x_t: float) -> np.ndarray:
        """P(s_t | x_1..t) a partir de P(s_{t-1} | x_1..t-1). Causal."""
        assert self.trans is not None and self.start is not None
        if not np.isfinite(x_t):
            return prev if prev is not None else self.start.copy()
        prior = self.start if prev is None else prev @ self.trans
        post = prior * self._emis(np.array([x_t]))[0]
        s = post.sum()
        return post / s if s > 0 else prior

    def filter(self, x: np.ndarray) -> np.ndarray:
        out = np.empty((len(x), self.k))
        p: np.ndarray | None = None
        for t, v in enumerate(np.asarray(x, dtype=float)):
            p = self.filter_step(p, v)
            out[t] = p
        return out
