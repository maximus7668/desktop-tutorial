"""Walk-forward con selección robusta de parámetros (meseta, no pico).

* Ventanas de entrenamiento/test por días de trading, con embargo entre ambas.
* En cada ventana se evalúa una rejilla PEQUEÑA de parámetros (cuantas menos
  combinaciones, menor el sesgo de selección; registra ``n_trials`` para el DSR).
* Se elige la combinación con mejor **mediana de su vecindario** en la rejilla:
  un óptimo aislado rodeado de malos resultados es casi siempre ruido.
* El resultado combinado out-of-sample es la única cifra que debe usarse para
  decidir si el sistema pasa a paper trading.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from propfut.backtest.engine import BacktestResult, run_backtest
from propfut.backtest.metrics import PropMetrics
from propfut.core.config import SystemConfig
from propfut.data.news import NewsCalendar

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WFSplit:
    train_start: date
    train_end: date
    test_start: date
    test_end: date


def walk_forward_splits(
    trade_dates: Sequence[date],
    train_days: int,
    test_days: int,
    step_days: int | None = None,
    embargo_days: int = 1,
    anchored: bool = False,
) -> list[WFSplit]:
    days = sorted(set(trade_dates))
    step = step_days or test_days
    out: list[WFSplit] = []
    i = 0
    while True:
        tr_s = 0 if anchored else i
        tr_e = i + train_days - 1
        te_s = tr_e + 1 + embargo_days
        te_e = te_s + test_days - 1
        if te_e >= len(days):
            break
        out.append(WFSplit(days[tr_s], days[tr_e], days[te_s], days[te_e]))
        i += step
    return out


def override(cfg: SystemConfig, params: Mapping[str, Any]) -> SystemConfig:
    """Devuelve una copia validada de ``cfg`` con claves anidadas ('ensemble.min_confidence')."""
    data = cfg.model_dump()
    for path, val in params.items():
        node = data
        keys = path.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = val
    return SystemConfig.model_validate(data)


def prop_objective(m: PropMetrics, min_trades: int = 8) -> float:
    """Objetivo orientado a prop firm: PnL / max DD, penalizando rupturas, inconsistencia y poca muestra."""
    if m.breached:
        return -10.0
    score = m.net_pnl / max(m.max_drawdown_usd, 200.0)
    if m.consistency_ok is False:
        score -= 0.5
    if m.n_trades < min_trades:
        score *= m.n_trades / min_trades
    score -= 2.0 * max(0.0, m.max_trailing_utilization - 0.5)
    return float(score)


@dataclass
class WFResult:
    splits: list[WFSplit]
    chosen: list[dict[str, Any]]
    is_scores: list[dict[str, float]]
    oos: list[BacktestResult]
    n_trials: int
    oos_daily: pd.DataFrame = field(default_factory=pd.DataFrame)

    def summary(self) -> pd.DataFrame:
        rows = []
        for s, p, r in zip(self.splits, self.chosen, self.oos, strict=True):
            m = r.metrics
            rows.append({
                "test": f"{s.test_start}..{s.test_end}", "params": p, "oos_pnl": round(m.net_pnl, 2),
                "trades": m.n_trades, "pf": round(m.profit_factor, 2), "max_dd": round(m.max_drawdown_usd, 2),
                "dd_util": round(m.max_trailing_utilization, 3), "breached": m.breached,
            })
        return pd.DataFrame(rows)


class WalkForwardOptimizer:
    def __init__(
        self,
        cfg: SystemConfig,
        market: Mapping[str, pd.DataFrame],
        param_grid: Mapping[str, Sequence[Any]],
        objective: Callable[[PropMetrics], float] = prop_objective,
        news: NewsCalendar | None = None,
        warmup_days: int = 10,
    ) -> None:
        self.cfg = cfg
        self.market = market
        self.grid = {k: list(v) for k, v in param_grid.items()}
        self.objective = objective
        self.news = news
        self.warmup = warmup_days
        self.keys = list(self.grid)
        self.combos = list(itertools.product(*(range(len(v)) for v in self.grid.values())))

    def _params(self, combo: tuple[int, ...]) -> dict[str, Any]:
        return {k: self.grid[k][i] for k, i in zip(self.keys, combo, strict=True)}

    def _robust_choice(self, scores: dict[tuple[int, ...], float]) -> tuple[int, ...]:
        def neigh(c: tuple[int, ...]) -> list[float]:
            vals = [scores[c]]
            for d in range(len(c)):
                for delta in (-1, 1):
                    n = list(c)
                    n[d] += delta
                    t = tuple(n)
                    if t in scores:
                        vals.append(scores[t])
            return vals
        return max(scores, key=lambda c: (float(np.median(neigh(c))), scores[c]))

    def run(self, splits: Sequence[WFSplit]) -> WFResult:
        chosen, is_scores, oos = [], [], []
        for k, sp in enumerate(splits):
            scores: dict[tuple[int, ...], float] = {}
            for combo in self.combos:
                cfg = override(self.cfg, self._params(combo))
                res = run_backtest(cfg, self.market, self.news, warmup_days=self.warmup,
                                   start=sp.train_start, end=sp.train_end)
                scores[combo] = self.objective(res.metrics)
            best = self._robust_choice(scores)
            params = self._params(best)
            log.info("Split %d: params=%s IS=%.3f", k, params, scores[best])
            res = run_backtest(override(self.cfg, params), self.market, self.news, warmup_days=self.warmup,
                               start=sp.test_start, end=sp.test_end)
            chosen.append(params)
            is_scores.append({str(self._params(c)): v for c, v in scores.items()})
            oos.append(res)
        daily = pd.concat([r.daily for r in oos if not r.daily.empty], ignore_index=True) if oos else pd.DataFrame()
        return WFResult(list(splits), chosen, is_scores, oos, len(self.combos) * max(1, len(splits)), daily)
