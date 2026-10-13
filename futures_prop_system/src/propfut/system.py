"""Orquestador: cablea datos -> régimen -> agentes -> ensemble -> policy -> riesgo -> ejecución.

El MISMO método :meth:`TradingSystem.on_timestamp` se usa en backtest, paper y
live, de forma que lo validado es exactamente lo que se ejecuta.

Orden de procesamiento por timestamp (barra que abre en ``ts``):

1. Inicio de día de trading (trailing EOD, reset de contadores).
2. Rollover de posiciones si el contrato activo cambió.
3. Fills de órdenes pendientes contra la barra (entradas a la apertura, luego stops/targets).
4. Mark-to-market pesimista (máximo antes que mínimo) y comprobación de reglas.
5. Circuit breakers del RiskEngine (flatten / halt).
6. Gestión de posiciones abiertas (breakeven, trailing, time stop) y salida por señal opuesta.
7. Nuevas decisiones al CIERRE de la barra -> órdenes que se ejecutan en la siguiente.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from propfut.agents import DynamicEnsemble, base_weights, build_agents
from propfut.agents.base import Agent, MarketContext
from propfut.agents.ensemble import EnsembleDecision
from propfut.contracts.calendar import ContractCalendar
from propfut.contracts.rollover import RolloverManager
from propfut.contracts.specs import ContractSpec
from propfut.core.config import SystemConfig
from propfut.core.sessions import SessionCalendar
from propfut.core.types import Bar, RunMode, Side
from propfut.data.features import FeatureFrame
from propfut.data.news import NewsCalendar, NewsState, SentimentProvider
from propfut.execution.broker import SimulatedBroker
from propfut.execution.manager import ExecutionManager
from propfut.monitoring.alerts import AlertLevel, AlertManager
from propfut.monitoring.logger import DecisionLogger
from propfut.policy.base import PolicyAction, PolicyContext, make_policy
from propfut.regime.detector import RegimeDetector
from propfut.risk.account import AccountState
from propfut.risk.engine import RiskActionType, RiskDecision, RiskEngine, TradeIntent

log = logging.getLogger(__name__)


class TradingSystem:
    def __init__(
        self,
        cfg: SystemConfig,
        news: NewsCalendar | None = None,
        sentiment: SentimentProvider | None = None,
        broker: SimulatedBroker | None = None,
        mode: RunMode | None = None,
        decision_log: DecisionLogger | None = None,
        alerts: AlertManager | None = None,
        holidays: Sequence[date] = (),
        stop_on_breach: bool = True,
    ) -> None:
        self.cfg = cfg
        self.mode = mode or cfg.execution.mode
        self.specs: dict[str, ContractSpec] = {r: ContractSpec(cfg.spec(r)) for r in cfg.instruments}
        self.sessions = {
            r: SessionCalendar(s.cfg.session.timezone, cfg.account.day_reset_time,
                               s.cfg.session.rth_open, s.cfg.session.rth_close)
            for r, s in self.specs.items()
        }
        self.calendars = {r: ContractCalendar(s, holidays) for r, s in self.specs.items()}
        self.rollers = {r: RolloverManager(c) for r, c in self.calendars.items()}
        self.news = news or NewsCalendar()
        self.sentiment = sentiment
        self.detector = RegimeDetector(cfg.regime)
        self.agents: dict[str, list[Agent]] = {r: build_agents(cfg, r) for r in cfg.instruments}
        weights = base_weights(cfg)
        self.ensembles = {r: DynamicEnsemble(a, cfg.ensemble, weights) for r, a in self.agents.items()}
        self.policy = make_policy(cfg.policy, cfg.ensemble, cfg.execution.default_entry)
        self.risk = RiskEngine(
            cfg.account, cfg.risk, self.specs, self.sessions, self.news,
            roll_guard=lambda root, td: self.rollers[root].entries_allowed(td),
        )
        self.account = AccountState(cfg.account)
        self.alerts = alerts or AlertManager()
        self.broker = broker or SimulatedBroker(
            self.specs, cfg.execution.limit_requires_trade_through, cfg.execution.max_participation_rate
        )
        self.exec = ExecutionManager(
            self.broker, self.specs, self.risk, cfg.execution, cfg.policy, self.mode,
            on_alert=lambda lvl, msg: self.alerts.emit(lvl, msg),
        )
        self.dlog = decision_log or DecisionLogger(None, enabled=False)
        self.stop_on_breach = stop_on_breach
        self.frames: dict[str, FeatureFrame] = {}
        self.last_close: dict[str, float] = {}
        self.last_contract: dict[str, str] = {}
        self.account_halted = False
        self.veto_counter: Counter[str] = Counter()
        self.decisions_made = 0
        self.last_decisions: dict[str, EnsembleDecision] = {}
        self.equity_curve: list[tuple[datetime, float, float, float, float]] = []
        #: contador monotónico de barras por raíz (independiente de ventanas deslizantes en live)
        self.bar_no: Counter[str] = Counter()
        #: duración de barra por raíz: ``ts`` es la APERTURA de la barra; se decide a su cierre
        self.bar_interval: dict[str, timedelta] = {}

    # ------------------------------------------------------------------ #
    def set_frames(self, frames: Mapping[str, FeatureFrame]) -> None:
        self.frames = dict(frames)
        for r, ff in self.frames.items():
            if len(ff) > 2:
                diffs = ff.index[1:] - ff.index[:-1]
                self.bar_interval[r] = pd.Timedelta(diffs[: min(len(diffs), 500)].median()).to_pytimedelta()

    def fit_models(self, train_bars: Mapping[str, int]) -> None:
        """Ajusta modelos estadísticos SOLO con las primeras ``train_bars`` barras de cada raíz."""
        for root, n in train_bars.items():
            ff = self.frames.get(root)
            if ff is not None and n > 0:
                self.detector.fit_hmm(root, ff.cols["rv"][:n])

    # ------------------------------------------------------------------ #
    def _news_state(self, root: str, ts: datetime) -> NewsState:
        lim = self.cfg.risk
        s = self.sentiment.score(root, ts) if self.sentiment else None
        return self.news.state(root, ts, lim.news_blackout_minutes_before, lim.news_blackout_minutes_after, s)

    def _peers(self, root: str, ts: datetime) -> dict[str, tuple[FeatureFrame, int]]:
        out = {}
        for r, ff in self.frames.items():
            if r != root:
                j = ff.position(ts)
                out[r] = (ff, -1 if j is None else j)
        return out

    def _bar(self, root: str, i: int) -> Bar:
        ff = self.frames[root]
        c = ff.cols
        return Bar(ff.index[i].to_pydatetime(), root, str(ff.contracts[i]), c["open"][i], c["high"][i],
                   c["low"][i], c["close"][i], c["volume"][i])

    # ------------------------------------------------------------------ #
    def decide(self, root: str, i: int, ts: datetime, track: bool = True) -> tuple[
        EnsembleDecision, PolicyAction, RiskDecision | None
    ]:
        """Pipeline de decisión al cierre de la barra ``i`` (sin efectos sobre órdenes)."""
        ff = self.frames[root]
        row = ff.row(i)
        news = self._news_state(root, ts)
        regime = self.detector.classify(root, row, news)
        # pares por timestamp de APERTURA de la barra (misma barra ya cerrada en todas las raíces);
        # usar ``ts`` (cierre) apuntaría a la barra siguiente aún abierta -> look-ahead
        bar_ts = ff.index[i].to_pydatetime()
        ctx = MarketContext(root, ts, i, ff, row, regime, news, self._peers(root, bar_ts))
        signals = [a(ctx) for a in self.agents[root]]
        ens = self.ensembles[root]
        if track:
            for s in signals:
                ens.tracker.record(root, s, self.bar_no[root], row["close"], row["atr"])
        decision = ens.combine(root, ts, signals, regime)
        self.last_decisions[root] = decision
        acc, lim = self.account, self.cfg.risk
        pctx = PolicyContext(
            acc.dd_utilization, acc.daily_pnl / lim.daily_loss_soft_stop_usd, acc.trades_today,
            acc.consecutive_losses, self.risk.account_cal.minutes_until(ts, self.cfg.account.flatten_time),
        )
        action = self.policy.decide(decision, pctx)
        if not action.take:
            return decision, action, None
        close = row["close"]
        atr = row.get("stop_vol", row["atr"])
        if not atr > 0:
            atr = row["atr"]
        side = Side.LONG if decision.direction > 0 else Side.SHORT
        intent = TradeIntent(
            root=root, contract=str(ff.contracts[i]), side=side, entry_price=close,
            stop_price=close - int(side) * action.stop_atr * atr,
            target_price=close + int(side) * action.target_atr * atr,
            ts=ts, size_fraction=action.size_fraction, confidence=decision.confidence,
            entry_type=action.entry_type, reason=decision.explain(), regime=regime.label.value,
        )
        marks = dict(self.last_close)
        rd = self.risk.evaluate(intent, acc, self.exec.position_risks(marks), self.exec.working_entry_qty())
        return decision, action, rd

    # ------------------------------------------------------------------ #
    def on_timestamp(self, ts: datetime, indices: Mapping[str, int]) -> None:
        """Procesa todas las raíces que tienen barra en ``ts`` (``indices`` = posición en su frame).

        ``ts`` es la apertura de la barra (los fills pendientes se ejecutan a ese precio);
        las reglas horarias y las nuevas decisiones se evalúan al CIERRE (``ts + intervalo``).
        """
        acc = self.account
        interval = max((self.bar_interval.get(r, timedelta(minutes=5)) for r in indices),
                       default=timedelta(minutes=5))
        now = ts + interval
        acc.start_day(self.risk.account_cal.trade_date(ts))
        bars = {r: self._bar(r, i) for r, i in indices.items()}
        for r in indices:
            self.bar_no[r] += 1

        # 2. rollover
        for r, b in bars.items():
            prev = self.last_contract.get(r)
            if prev is not None and prev != b.contract:
                pos = self.exec.position(r)
                if pos is not None:
                    policy = self.specs[r].cfg.roll.position_policy
                    self.exec.roll_position(r, b.contract, 0.0, ts, policy)
                    self.dlog.log("roll", ts, root=r, frm=prev, to=b.contract, policy=policy)
            self.last_contract[r] = b.contract

        # 3. fills (antes: equity máxima alcanzable por las posiciones abiertas al inicio de la barra)
        pre_hi = acc.balance + self.exec.open_pnl_range(
            {r: b.low for r, b in bars.items()}, {r: b.high for r, b in bars.items()}
        )[1] + sum(
            self.specs[r].pnl(p.avg_price, self.last_close.get(r, p.avg_price), p.qty)
            for r, p in self.exec.positions.items() if p.qty and r not in bars
        )
        for r, b in bars.items():
            fills = self.broker.process_bar(b)
            closed = self.exec.on_fills(fills, acc)
            fills2 = self.broker.process_exits(b)
            closed += self.exec.on_fills(fills2, acc)
            for f in fills + fills2:
                self.dlog.log("fill", ts, root=f.root, tag=f.tag, side=f.side.name, qty=f.qty, price=f.price,
                              slippage_ticks=f.slippage_ticks)
            for t in closed:
                self.dlog.log("trade_closed", ts, **t.to_dict())
            self.last_close[r] = b.close

        # 4. mark-to-market pesimista
        lows = {r: b.low for r, b in bars.items()}
        highs = {r: b.high for r, b in bars.items()}
        for r in self.exec.positions:
            lows.setdefault(r, self.last_close.get(r, 0.0))
            highs.setdefault(r, self.last_close.get(r, 0.0))
        lo, hi = self.exec.open_pnl_range(lows, highs)
        acc.mark(self.exec.open_pnl(self.last_close), ts, lo, hi, equity_high=pre_hi)
        self.alerts.check_drawdown(acc.dd_utilization, self.cfg.monitoring.dd_alert_levels, ts)

        # 5. circuit breakers
        positions = self.exec.position_risks(self.last_close)
        for a in self.risk.check_circuit_breakers(acc, positions, now, interval):
            if a.kind in (RiskActionType.FLATTEN_ALL, RiskActionType.FLATTEN_ROOTS):
                roots = a.roots if a.kind is RiskActionType.FLATTEN_ROOTS else None
                if self.exec.flatten(roots, a.reason, now):
                    self.dlog.log("risk_action", now, action=a.kind.value, reason=a.reason, roots=a.roots)
                    self.alerts.emit(AlertLevel.WARNING, f"{a.kind.value}: {a.reason}", ts=now)
            elif a.kind is RiskActionType.HALT_ACCOUNT and not self.account_halted:
                self.account_halted = True
                self.dlog.log("risk_action", now, action=a.kind.value, reason=a.reason)
                self.alerts.emit(AlertLevel.CRITICAL, f"CUENTA DETENIDA: {a.reason}", ts=now)
        self.equity_curve.append((ts, acc.equity, acc.balance, acc.threshold, acc.daily_pnl))
        if self.account_halted and self.stop_on_breach:
            return

        # 6-7. gestión y nuevas decisiones al cierre de la barra
        td = self.risk.account_cal.trade_date(now)
        for r, i in indices.items():
            ff = self.frames[r]
            row_close, atr = ff.cols["close"][i], ff.cols["atr"][i]
            self.exec.on_bar_end(r, row_close, ff.cols["high"][i], ff.cols["low"][i], atr, now)
            self.ensembles[r].tracker.resolve(r, self.bar_no[r], row_close)
            if self.cfg.risk.rth_only_entries and not ff.cols["is_rth"][i] and self.exec.position(r) is None:
                continue  # fuera de RTH sólo se gestiona; no hay entradas
            decision, action, rd = self.decide(r, i, now)
            self.decisions_made += 1
            pos = self.exec.position(r)
            if pos is not None:
                if decision.direction != 0 and decision.direction * pos.qty < 0 and \
                        decision.confidence >= self.cfg.ensemble.exit_threshold:
                    self.exec.flatten([r], "señal opuesta", now)
                    self.dlog.log("exit_signal", now, root=r, explanation=decision.explain())
                continue
            if rd is None or self.account_halted or self.risk.is_halted(td):
                continue
            if not rd.approved:
                self.veto_counter[rd.reasons[0].split(":")[0].split("(")[0].strip()] += 1
                self.dlog.log("veto", now, root=r, reasons=rd.reasons, checks=dict(rd.checks),
                              ensemble=decision.explain())
                continue
            meta = {"regime": decision.regime.label.value, "confidence": decision.confidence,
                    "explanation": decision.explain()}
            res = self.exec.submit_decision(rd, now, meta)
            self.dlog.log("order", now, root=r, decision=rd.summary(), checks=dict(rd.checks),
                          ensemble=decision.explain(), policy=action.reason, submitted=res is not None)
        if self.mode is RunMode.LIVE_PROPOSAL:
            self.exec.expire_proposals(now)

    # ------------------------------------------------------------------ #
    def state(self, ts: datetime) -> dict[str, Any]:
        return {
            "ts": ts.isoformat(),
            "mode": self.mode.value,
            "account": self.account.snapshot(),
            "risk": self.risk.snapshot(ts),
            "positions": [
                {"root": p.root, "contract": p.contract, "qty": p.qty, "avg_price": round(p.avg_price, 6),
                 "stop_price": p.stop_price, "target_price": p.target_price}
                for p in self.exec.positions.values() if p.qty
            ],
            "working_orders": [
                {"id": o.id, "root": o.root, "tag": o.tag, "type": o.type.value, "side": o.side.name,
                 "qty": o.remaining, "limit": o.limit_price, "stop": o.stop_price}
                for o in self.broker.open_orders()
            ],
            "proposals": [
                {"id": p.id, "summary": p.decision.summary(), "expires": p.expires.isoformat()}
                for p in self.exec.proposals.values() if p.status == "PENDING"
            ],
            "agent_stats": {k: v for e in self.ensembles.values() for k, v in e.tracker.stats().items()},
            "recent_decisions": [
                {"root": r, "ts": d.ts.isoformat(), "summary": d.explain()} for r, d in self.last_decisions.items()
            ],
            "equity_curve": [
                {"ts": t.isoformat(), "equity": e, "threshold": th} for t, e, _, th, _ in self.equity_curve[-500:]
            ],
        }


def iterate_timeline(frames: Mapping[str, FeatureFrame]) -> Iterable[tuple[datetime, dict[str, int]]]:
    """Recorre la unión de timestamps de todas las raíces (merge ordenado)."""
    import heapq

    heap: list[tuple[Any, str, int]] = []
    for r, ff in frames.items():
        if len(ff):
            heapq.heappush(heap, (ff.index[0], r, 0))
    while heap:
        ts = heap[0][0]
        group: dict[str, int] = {}
        while heap and heap[0][0] == ts:
            _, r, i = heapq.heappop(heap)
            group[r] = i
            if i + 1 < len(frames[r]):
                heapq.heappush(heap, (frames[r].index[i + 1], r, i + 1))
        yield ts.to_pydatetime(), group
