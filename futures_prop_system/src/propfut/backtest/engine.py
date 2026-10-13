"""Backtest event-driven sobre series continuas ajustadas, usando el MISMO orquestador que live."""

from __future__ import annotations

import time as _time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

from propfut.backtest.metrics import PropMetrics, compute_metrics
from propfut.core.config import SystemConfig
from propfut.core.types import Bar, RunMode
from propfut.data.features import FeatureFrame
from propfut.data.news import NewsCalendar, SentimentProvider
from propfut.execution.orders import TradeRecord
from propfut.monitoring.alerts import AlertManager
from propfut.monitoring.logger import DecisionLogger
from propfut.system import TradingSystem, iterate_timeline


@dataclass
class BacktestResult:
    metrics: PropMetrics
    trades: list[TradeRecord]
    daily: pd.DataFrame
    equity: pd.DataFrame
    vetoes: Counter[str]
    agent_stats: dict[str, dict[str, float]]
    decisions: int
    elapsed_s: float
    system: TradingSystem = field(repr=False)

    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.to_dict() for t in self.trades])

    def summary(self) -> str:
        v = ", ".join(f"{k} x{n}" for k, n in self.vetoes.most_common(6)) or "-"
        return (
            f"Backtest: {self.metrics.n_trades} trades, {self.decisions} decisiones, {self.elapsed_s:.1f}s\n"
            f"{self.metrics.report()}\n  vetos principales: {v}"
        )


def run_backtest(
    cfg: SystemConfig,
    market: Mapping[str, pd.DataFrame],
    news: NewsCalendar | None = None,
    sentiment: SentimentProvider | None = None,
    warmup_days: int = 10,
    start: date | None = None,
    end: date | None = None,
    slippage_multiplier: float = 1.0,
    log_dir: str | None = None,
    holidays: Sequence[date] = (),
    stop_on_breach: bool = True,
) -> BacktestResult:
    """Ejecuta un backtest.

    ``market``: raíz -> DataFrame de features (salida de ``prepare_market_data``).
    Los primeros ``warmup_days`` días de trading sólo sirven para calentar
    indicadores y ajustar el HMM: no se opera en ellos.
    ``start``/``end`` (días de trading) recortan el periodo operado (para walk-forward).
    """
    t0 = _time.perf_counter()
    frames: dict[str, FeatureFrame] = {}
    for root in cfg.instruments:
        if root not in market:
            raise KeyError(f"Faltan datos para {root}")
        df = market[root]
        if end is not None:
            df = df[pd.to_datetime(df["trade_date"]) <= pd.Timestamp(end)]
        frames[root] = FeatureFrame.from_frame(root, df)

    dlog = DecisionLogger(log_dir, enabled=log_dir is not None)
    system = TradingSystem(cfg, news=news, sentiment=sentiment, mode=RunMode.BACKTEST, decision_log=dlog,
                           alerts=AlertManager(channels=[]), holidays=holidays, stop_on_breach=stop_on_breach)
    if slippage_multiplier != 1.0:
        system.broker.slip_mult = slippage_multiplier
    system.set_frames(frames)

    # periodo de calentamiento: primeros días de trading de cada raíz
    warm: dict[str, int] = {}
    first_trade_day: date | None = None
    for root, ff in frames.items():
        days = np.unique(ff.trade_dates)
        cut = days[min(warmup_days, len(days) - 1)] if len(days) else None
        if start is not None:
            s = np.datetime64(start)
            cut = max(cut, s) if cut is not None else s
        n = int(np.searchsorted(ff.trade_dates, cut)) if cut is not None else 0
        warm[root] = n
        if cut is not None:
            d = pd.Timestamp(cut).date()
            first_trade_day = d if first_trade_day is None else max(first_trade_day, d)
    system.fit_models(warm)

    for ts, idx in iterate_timeline(frames):
        if first_trade_day is not None and system.risk.account_cal.trade_date(ts) < first_trade_day:
            # sólo se calientan los agentes de rendimiento/regímenes (sin operar ni contar la cuenta)
            for r, i in idx.items():
                system.last_close[r] = frames[r].cols["close"][i]
                system.last_contract[r] = str(frames[r].contracts[i])
            continue
        system.on_timestamp(ts, idx)
        if system.account_halted and stop_on_breach and system.account.breached:
            break

    # cerrar lo que quede abierto al final (al último precio conocido)
    acc = system.account
    if system.exec.positions and any(p.qty for p in system.exec.positions.values()):
        last_ts = system.equity_curve[-1][0] if system.equity_curve else datetime.now()
        system.exec.flatten(None, "fin de backtest", last_ts)
        for r, ff in frames.items():
            c = float(ff.cols["close"][-1])  # se liquida al último cierre conocido
            b = Bar(ff.index[-1].to_pydatetime(), r, str(ff.contracts[-1]), c, c, c, c, float(ff.cols["volume"][-1]))
            system.exec.on_fills(system.broker.process_bar(b), acc)
    acc.finalize()
    dlog.close()

    eq = pd.DataFrame(system.equity_curve, columns=["ts", "equity", "balance", "threshold", "daily_pnl"])
    eq = eq.set_index("ts") if not eq.empty else eq
    daily = pd.DataFrame(acc.history_dicts())
    if not daily.empty:
        daily = daily[daily["trade_date"] >= (first_trade_day or daily["trade_date"].min())]
    metrics = compute_metrics(system.exec.trades, daily, eq, cfg.account, acc.breached, acc.breach_reason,
                              acc.total_commissions)
    stats = {k: v for e in system.ensembles.values() for k, v in e.tracker.stats().items()}
    return BacktestResult(metrics, list(system.exec.trades), daily, eq, system.veto_counter, stats,
                          system.decisions_made, _time.perf_counter() - t0, system)
