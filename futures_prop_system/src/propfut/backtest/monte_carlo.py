"""Monte Carlo de la evaluación de la prop firm y stress testing.

Remuestrea **días completos** (no trades sueltos) con bootstrap por bloques para
conservar la autocorrelación y la forma intradía (mínimo y máximo de equity de
cada día). Así se simula correctamente el trailing intradía/EOD y el límite
diario, que dependen del recorrido intradía y no sólo del cierre.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from propfut.core.config import PropFirmRules, TrailingMode


@dataclass(frozen=True)
class MCResult:
    n_sims: int
    p_pass: float
    p_bust: float
    p_timeout: float
    median_days_to_pass: float | None
    p5_final_pnl: float
    p50_final_pnl: float
    p95_final_pnl: float
    p95_max_dd_utilization: float
    p99_max_dd_utilization: float
    expected_final_pnl: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def days_from_history(daily: pd.DataFrame) -> np.ndarray:
    """Convierte el histórico diario del backtest en matriz (pnl, low, high) relativa al inicio del día."""
    if daily.empty:
        return np.zeros((0, 3))
    start = daily["start_balance"].to_numpy(float)
    pnl = daily["pnl"].to_numpy(float)
    low = np.minimum(daily["min_equity"].to_numpy(float) - start, np.minimum(pnl, 0.0))
    high = np.maximum(daily["max_equity"].to_numpy(float) - start, np.maximum(pnl, 0.0))
    return np.column_stack([pnl, low, high])


class PropChallengeSimulator:
    def __init__(self, rules: PropFirmRules) -> None:
        self.rules = rules

    def _block_indices(self, rng: np.random.Generator, n: int, length: int, block: int) -> np.ndarray:
        out: list[int] = []
        while len(out) < length:
            s = int(rng.integers(0, n))
            out.extend(((s + np.arange(block)) % n).tolist())
        return np.asarray(out[:length])

    def run_one(self, days: np.ndarray) -> tuple[str, int, float, float]:
        """Simula una trayectoria. Devuelve (resultado, días, pnl final, máx. utilización DD)."""
        r = self.rules
        bal = r.account_size
        hwm = bal
        thr = r.initial_threshold
        lock = r.trailing_lock_level
        max_util = 0.0
        pnls: list[float] = []

        def raise_thr(level: float) -> float:
            new = level - r.max_loss
            if lock is not None:
                new = min(new, lock)
            return max(thr, new)

        for d, (pnl, low, high) in enumerate(days, start=1):
            if r.trailing_mode is TrailingMode.INTRADAY:
                hwm = max(hwm, bal + high)  # pesimista: máximo antes que mínimo
                thr = raise_thr(hwm)
            eq_low = bal + low
            max_util = max(max_util, min(1.0, max(0.0, 1 - (eq_low - thr) / r.max_loss)))
            if eq_low <= thr:
                return "bust", d, eq_low - r.account_size, 1.0
            if r.daily_loss_limit is not None and low <= -r.daily_loss_limit:
                if r.daily_loss_mode == "breach":
                    return "bust", d, bal + low - r.account_size, max_util
                pnl = max(pnl, -r.daily_loss_limit)  # la firma liquida en el límite
            bal += pnl
            pnls.append(pnl)
            if r.trailing_mode is TrailingMode.END_OF_DAY:
                hwm = max(hwm, bal)
                thr = raise_thr(hwm)
            total = bal - r.account_size
            if total >= r.profit_target and d >= r.min_trading_days:
                share = max(pnls) / total if total > 0 else 1.0
                if r.consistency_max_day_share is None or share <= r.consistency_max_day_share:
                    return "pass", d, total, max_util
        return "timeout", len(days), bal - r.account_size, max_util

    def simulate(
        self,
        days: np.ndarray,
        n_sims: int = 5000,
        max_days: int = 60,
        block: int = 5,
        seed: int = 0,
    ) -> MCResult:
        if len(days) == 0:
            raise ValueError("No hay días para simular")
        rng = np.random.default_rng(seed)
        outcomes, ndays, finals, utils = [], [], [], []
        for _ in range(n_sims):
            idx = self._block_indices(rng, len(days), max_days, min(block, len(days)))
            o, d, f, u = self.run_one(days[idx])
            outcomes.append(o)
            ndays.append(d)
            finals.append(f)
            utils.append(u)
        oc = np.asarray(outcomes)
        nd = np.asarray(ndays)
        fi = np.asarray(finals)
        ut = np.asarray(utils)
        passed = oc == "pass"
        return MCResult(
            n_sims=n_sims,
            p_pass=float(passed.mean()),
            p_bust=float((oc == "bust").mean()),
            p_timeout=float((oc == "timeout").mean()),
            median_days_to_pass=float(np.median(nd[passed])) if passed.any() else None,
            p5_final_pnl=float(np.percentile(fi, 5)),
            p50_final_pnl=float(np.percentile(fi, 50)),
            p95_final_pnl=float(np.percentile(fi, 95)),
            p95_max_dd_utilization=float(np.percentile(ut, 95)),
            p99_max_dd_utilization=float(np.percentile(ut, 99)),
            expected_final_pnl=float(fi.mean()),
        )


# --------------------------------------------------------------------------- #
# Stress testing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StressScenario:
    name: str
    extra_cost_per_trade: float = 0.0  # USD por operación (slippage/comisiones extra)
    pnl_haircut: float = 0.0  # fracción restada a los días ganadores
    vol_multiplier: float = 1.0  # escala pnl/low/high
    shock_day_loss: float | None = None  # inserta un día de gap con esta pérdida (USD)
    shock_every_n_days: int = 20


def apply_stress(days: np.ndarray, trades_per_day: np.ndarray, sc: StressScenario) -> np.ndarray:
    d = days.copy() * sc.vol_multiplier
    cost = trades_per_day * sc.extra_cost_per_trade
    d[:, 0] -= cost
    d[:, 1] = np.minimum(d[:, 1] - cost, d[:, 0])
    if sc.pnl_haircut:
        win = d[:, 0] > 0
        d[win, 0] *= 1 - sc.pnl_haircut
        d[win, 2] *= 1 - sc.pnl_haircut
    if sc.shock_day_loss is not None:
        n = max(1, len(d) // sc.shock_every_n_days)
        shock = np.tile([-sc.shock_day_loss, -sc.shock_day_loss, 0.0], (n, 1))
        d = np.vstack([d, shock])
    return d


DEFAULT_SCENARIOS: Sequence[StressScenario] = (
    StressScenario("base"),
    StressScenario("slippage +1 tick/lado (MES≈2.5$/trade)", extra_cost_per_trade=2.5),
    StressScenario("slippage x3 (≈7.5$/trade)", extra_cost_per_trade=7.5),
    StressScenario("ganancias -25%", pnl_haircut=0.25),
    StressScenario("volatilidad x1.5", vol_multiplier=1.5),
    StressScenario("gap de 500$ cada 20 días", shock_day_loss=500.0),
    StressScenario("combinado", extra_cost_per_trade=5.0, pnl_haircut=0.2, vol_multiplier=1.3, shock_day_loss=400.0),
)


def stress_suite(
    daily: pd.DataFrame,
    rules: PropFirmRules,
    scenarios: Sequence[StressScenario] = DEFAULT_SCENARIOS,
    n_sims: int = 2000,
    max_days: int = 60,
    seed: int = 0,
) -> pd.DataFrame:
    days = days_from_history(daily)
    tpd = daily["trades"].to_numpy(float) if not daily.empty else np.zeros(0)
    sim = PropChallengeSimulator(rules)
    rows = []
    for sc in scenarios:
        d = apply_stress(days, tpd, sc)
        res = sim.simulate(d, n_sims=n_sims, max_days=max_days, seed=seed)
        rows.append({"escenario": sc.name, "P(pass)": res.p_pass, "P(bust)": res.p_bust,
                     "P(timeout)": res.p_timeout, "pnl_p5": res.p5_final_pnl, "pnl_p50": res.p50_final_pnl,
                     "dd_util_p95": res.p95_max_dd_utilization})
    return pd.DataFrame(rows)


def trade_sequence_drawdowns(trade_pnls: Sequence[float], n_sims: int = 5000, seed: int = 0) -> np.ndarray:
    """Distribución del máximo drawdown permutando el orden de las operaciones."""
    rng = np.random.default_rng(seed)
    x = np.asarray(trade_pnls, dtype=float)
    out = np.empty(n_sims)
    for k in range(n_sims):
        eq = np.cumsum(rng.permutation(x))
        peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
        out[k] = float((peak - eq).max()) if len(eq) else 0.0
    return out
