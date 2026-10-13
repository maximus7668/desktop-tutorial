"""Herramientas anti-overfitting.

* Probabilistic Sharpe Ratio y Deflated Sharpe Ratio (Bailey & López de Prado, 2014).
* Probability of Backtest Overfitting vía CSCV (Bailey, Borwein, López de Prado, Zhu, 2015).
* Minimum Track Record Length.

Regla práctica: si has probado N configuraciones, el Sharpe observado del
mejor debe superar el Sharpe máximo esperado por azar entre N intentos.
"""

from __future__ import annotations

import itertools
import math
from statistics import NormalDist

import numpy as np

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


def _moments(returns: np.ndarray) -> tuple[float, float, float, int]:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 3:
        raise ValueError("Se necesitan >= 3 observaciones")
    mu, sd = r.mean(), r.std(ddof=1)
    if sd == 0:
        return 0.0, 0.0, 3.0, n
    z = (r - mu) / sd
    return float(mu / sd), float((z**3).mean()), float((z**4).mean()), n


def probabilistic_sharpe_ratio(
    sr: float, n: int, skew: float = 0.0, kurt: float = 3.0, sr_benchmark: float = 0.0
) -> float:
    """P(SR verdadero > sr_benchmark). ``sr`` y ``sr_benchmark`` NO anualizados (por observación)."""
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    if denom <= 0 or n < 2:
        return float("nan")
    return float(_N.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom)))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Sharpe máximo esperado entre ``n_trials`` estrategias sin habilidad (SR verdadero = 0)."""
    if n_trials < 2:
        return 0.0
    a = _N.inv_cdf(1 - 1 / n_trials)
    b = _N.inv_cdf(1 - 1 / (n_trials * math.e))
    return math.sqrt(var_sr) * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)


def deflated_sharpe_ratio(returns: np.ndarray, n_trials: int, var_trials_sr: float) -> float:
    """DSR: PSR usando como referencia el máximo esperado por azar entre ``n_trials`` pruebas.

    ``var_trials_sr``: varianza de los Sharpe (por observación) de todas las configuraciones probadas.
    """
    sr, skew, kurt, n = _moments(returns)
    return probabilistic_sharpe_ratio(sr, n, skew, kurt, expected_max_sharpe(n_trials, var_trials_sr))


def min_track_record_length(
    returns: np.ndarray, sr_benchmark: float = 0.0, confidence: float = 0.95
) -> float:
    """Nº mínimo de observaciones para que SR > benchmark con la confianza dada."""
    sr, skew, kurt, _ = _moments(returns)
    if sr <= sr_benchmark:
        return float("inf")
    z = _N.inv_cdf(confidence)
    return float(1 + (1 - skew * sr + (kurt - 1) / 4 * sr**2) * (z / (sr - sr_benchmark)) ** 2)


def pbo_cscv(perf: np.ndarray, n_splits: int = 16, max_combinations: int = 5000, seed: int = 0) -> dict[str, float]:
    """Probability of Backtest Overfitting.

    ``perf``: matriz T x N (T periodos, p.ej. PnL diario; N configuraciones).
    Para cada combinación de mitades de los ``n_splits`` bloques se elige la mejor
    configuración in-sample y se mira su rango out-of-sample. PBO = fracción de
    veces que la mejor IS queda por debajo de la mediana OOS.
    """
    m = np.asarray(perf, dtype=float)
    t, n = m.shape
    if n < 2:
        raise ValueError("Se necesitan >= 2 configuraciones")
    s = n_splits - (n_splits % 2)
    if t < s * 2:
        raise ValueError("Pocos periodos para el número de bloques")
    blocks = np.array_split(np.arange(t), s)
    combos = list(itertools.combinations(range(s), s // 2))
    rng = np.random.default_rng(seed)
    if len(combos) > max_combinations:
        sel = rng.choice(len(combos), max_combinations, replace=False)
        combos = [combos[i] for i in sel]

    def sharpe(x: np.ndarray) -> np.ndarray:
        sd = x.std(axis=0, ddof=1)
        sd[sd == 0] = np.inf
        return x.mean(axis=0) / sd

    logits = []
    for c in combos:
        is_idx = np.concatenate([blocks[i] for i in c])
        oos_idx = np.concatenate([blocks[i] for i in range(s) if i not in c])
        best = int(np.argmax(sharpe(m[is_idx])))
        oos = sharpe(m[oos_idx])
        rank = (oos < oos[best]).sum() + 0.5 * ((oos == oos[best]).sum() - 1)
        w = (rank + 0.5) / n  # rango relativo en (0, 1)
        logits.append(math.log(w / (1 - w)))
    lg = np.asarray(logits)
    return {"pbo": float((lg <= 0).mean()), "logit_median": float(np.median(lg)), "n_combinations": float(len(lg))}
