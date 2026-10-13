"""Métricas relevantes para cuentas de fondeo.

Además de las clásicas (profit factor, expectancy, Sharpe), se miden las que
deciden si una cuenta sobrevive: peor día, utilización máxima del drawdown
trailing, consistencia (mejor día / total), días hasta objetivo y violaciones.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from propfut.core.config import PropFirmRules
from propfut.execution.orders import TradeRecord


@dataclass(frozen=True)
class PropMetrics:
    net_pnl: float
    return_pct: float
    n_trades: int
    win_rate: float
    profit_factor: float
    expectancy_per_trade: float
    expectancy_per_contract: float
    avg_win: float
    avg_loss: float
    payoff_ratio: float
    avg_r_multiple: float
    max_drawdown_usd: float
    max_drawdown_pct_of_allowance: float
    max_trailing_utilization: float
    min_trailing_room: float
    worst_day: float
    best_day: float
    best_day_share: float | None
    pct_profitable_days: float
    trading_days: int
    avg_trades_per_day: float
    sharpe_daily_ann: float
    sortino_daily_ann: float
    max_consecutive_losses: int
    days_to_target: int | None
    breached: bool
    breach_reason: str
    consistency_ok: bool | None
    total_commissions: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def report(self) -> str:
        d = self.to_dict()
        w = max(len(k) for k in d)
        lines = []
        for k, v in d.items():
            if isinstance(v, float):
                v = f"{v:,.4f}" if abs(v) < 10 else f"{v:,.2f}"
            lines.append(f"  {k:<{w}} : {v}")
        return "\n".join(lines)


def _max_streak(xs: Sequence[float]) -> int:
    best = cur = 0
    for x in xs:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def compute_metrics(
    trades: Sequence[TradeRecord],
    daily: pd.DataFrame,
    equity: pd.DataFrame,
    rules: PropFirmRules,
    breached: bool = False,
    breach_reason: str = "",
    total_commissions: float = 0.0,
) -> PropMetrics:
    """``daily``: columnas ``trade_date, pnl, trades, min_equity, threshold_eod``.
    ``equity``: índice ts, columnas ``equity, threshold``."""
    pnls = np.array([t.net_pnl for t in trades], dtype=float)
    qtys = np.array([t.qty for t in trades], dtype=float)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    pf = gw / gl if gl > 0 else (math.inf if gw > 0 else 0.0)
    net = float(pnls.sum()) if len(pnls) else 0.0
    if not equity.empty:
        net = float(equity["equity"].iloc[-1] - rules.account_size)

    if not equity.empty:
        eq = equity["equity"].to_numpy()
        peak = np.maximum.accumulate(np.concatenate([[rules.account_size], eq]))[1:]
        max_dd = float((peak - eq).max())
        room = eq - equity["threshold"].to_numpy()
        min_room = float(room.min())
        util = float(np.clip(1 - room / rules.max_loss, 0, 1).max())
    else:
        max_dd, min_room, util = 0.0, rules.max_loss, 0.0

    dp = daily["pnl"].to_numpy(dtype=float) if not daily.empty else np.array([])
    active = daily[daily["trades"] > 0] if not daily.empty else daily
    total_pos = dp.sum()
    best_share = float(dp.max() / total_pos) if len(dp) and total_pos > 0 else None
    sd = dp.std(ddof=1) if len(dp) > 1 else 0.0
    downside = dp[dp < 0]
    dsd = math.sqrt((downside**2).mean()) if len(downside) else 0.0
    cum = np.cumsum(dp) if len(dp) else np.array([])
    hit = np.where(cum >= rules.profit_target)[0] if rules.profit_target > 0 else np.array([])
    days_to_target = int(hit[0] + 1) if len(hit) and not breached else None
    consistency = None
    if rules.consistency_max_day_share is not None and best_share is not None:
        consistency = best_share <= rules.consistency_max_day_share

    n = len(pnls)
    return PropMetrics(
        net_pnl=net,
        return_pct=net / rules.account_size,
        n_trades=n,
        win_rate=len(wins) / float(n) if n else 0.0,
        profit_factor=float(pf),
        expectancy_per_trade=float(pnls.mean()) if n else 0.0,
        expectancy_per_contract=float(pnls.sum()) / float(qtys.sum()) if n and qtys.sum() > 0 else 0.0,
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        payoff_ratio=float(wins.mean()) / float(-losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else 0.0,
        avg_r_multiple=float(np.mean([t.r_multiple for t in trades])) if n else 0.0,
        max_drawdown_usd=max_dd,
        max_drawdown_pct_of_allowance=max_dd / rules.max_loss,
        max_trailing_utilization=util,
        min_trailing_room=min_room,
        worst_day=float(dp.min()) if len(dp) else 0.0,
        best_day=float(dp.max()) if len(dp) else 0.0,
        best_day_share=best_share,
        pct_profitable_days=float((active["pnl"] > 0).mean()) if len(active) else 0.0,
        trading_days=int(len(active)),
        avg_trades_per_day=n / float(len(active)) if len(active) else 0.0,
        sharpe_daily_ann=float(dp.mean() / sd * math.sqrt(252)) if sd > 0 else 0.0,
        sortino_daily_ann=float(dp.mean() / dsd * math.sqrt(252)) if dsd > 0 else 0.0,
        max_consecutive_losses=_max_streak(pnls.tolist()),
        days_to_target=days_to_target,
        breached=breached,
        breach_reason=breach_reason,
        consistency_ok=consistency,
        total_commissions=total_commissions,
    )
