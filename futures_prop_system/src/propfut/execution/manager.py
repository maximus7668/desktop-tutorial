"""Execution & Contract Manager.

Responsabilidades:

* Convertir un :class:`RiskDecision` aprobado en un **bracket** (entrada + stop + target OCO).
  Nunca existe una entrada sin stop asociado.
* Modo ``LIVE_PROPOSAL``: la orden queda como propuesta con caducidad; al
  confirmarla se **re-evalúa** con el RiskEngine (el estado pudo cambiar).
* Modo ``LIVE_AUTO``: limitador de órdenes/minuto y kill switch.
* Modo ``ANALYSIS``: no envía nada.
* Sincronizar posiciones con los fills (parciales incluidos), mantener las
  órdenes de salida con la cantidad exacta de la posición y registrar operaciones.
* Gestión de la posición: breakeven, trailing por ATR (sólo se estrecha), time stop.
* Rollover de posiciones abiertas (cerrar o rolar al siguiente contrato).
* Vigilar slippage anómalo y reportarlo al RiskEngine.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from propfut.contracts.specs import ContractSpec
from propfut.core.config import ExecutionConfig, PolicyConfig
from propfut.core.types import OrderStatus, OrderType, RunMode, Side
from propfut.execution.broker import SimulatedBroker
from propfut.execution.orders import Fill, Order, Position, TradeRecord, next_id
from propfut.risk.account import AccountState
from propfut.risk.engine import PositionRisk, RiskDecision, RiskEngine

log = logging.getLogger(__name__)


@dataclass
class Proposal:
    id: str
    decision: RiskDecision
    created: datetime
    expires: datetime
    meta: dict[str, object] = field(default_factory=dict)
    status: str = "PENDING"  # PENDING | CONFIRMED | REJECTED | EXPIRED


@dataclass
class _Bracket:
    entry_id: str
    stop_id: str
    target_id: str | None
    meta: dict[str, object]


class ExecutionManager:
    def __init__(
        self,
        broker: SimulatedBroker,
        specs: Mapping[str, ContractSpec],
        risk: RiskEngine,
        cfg: ExecutionConfig,
        policy_cfg: PolicyConfig | None = None,
        mode: RunMode | None = None,
        on_alert: Callable[[str, str], None] | None = None,
    ) -> None:
        self.broker = broker
        self.specs = specs
        self.risk = risk
        self.cfg = cfg
        self.pcfg = policy_cfg or PolicyConfig()
        self.mode = mode or cfg.mode
        self.on_alert = on_alert or (lambda level, msg: log.warning("[%s] %s", level, msg))
        self.positions: dict[str, Position] = {}
        self.proposals: dict[str, Proposal] = {}
        self.trades: list[TradeRecord] = []
        self._open_trades: dict[str, TradeRecord] = {}
        self._brackets: dict[str, _Bracket] = {}  # root -> bracket vigente
        self._order_times: deque[datetime] = deque()
        self._slippage: deque[float] = deque(maxlen=50)

    # ------------------------------------------------------------------ #
    # Vistas
    # ------------------------------------------------------------------ #
    def position(self, root: str) -> Position | None:
        p = self.positions.get(root)
        return p if p and p.qty != 0 else None

    def position_risks(self, marks: Mapping[str, float]) -> list[PositionRisk]:
        out = []
        for root, p in self.positions.items():
            if p.qty == 0:
                continue
            out.append(PositionRisk(root, p.contract, p.qty, p.avg_price, p.stop_price,
                                    marks.get(root, p.avg_price)))
        return out

    def working_entry_qty(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for o in self.broker.open_orders():
            if o.tag == "entry":
                out[o.root] = out.get(o.root, 0) + o.remaining
        for p in self.proposals.values():
            if p.status == "PENDING":
                r = p.decision.intent.root
                out[r] = out.get(r, 0) + p.decision.qty
        return out

    def open_pnl(self, marks: Mapping[str, float]) -> float:
        tot = 0.0
        for root, p in self.positions.items():
            if p.qty and root in marks:
                tot += self.specs[root].pnl(p.avg_price, marks[root], p.qty)
        return tot

    def open_pnl_range(self, lows: Mapping[str, float], highs: Mapping[str, float]) -> tuple[float, float]:
        """(peor, mejor) PnL abierto dentro de la barra, posición a posición."""
        lo = hi = 0.0
        for root, p in self.positions.items():
            if not p.qty or root not in lows:
                continue
            spec = self.specs[root]
            a = spec.pnl(p.avg_price, lows[root], p.qty)
            b = spec.pnl(p.avg_price, highs[root], p.qty)
            lo += min(a, b)
            hi += max(a, b)
        return lo, hi

    # ------------------------------------------------------------------ #
    # Envío
    # ------------------------------------------------------------------ #
    def _rate_ok(self, now: datetime, n: int) -> bool:
        while self._order_times and now - self._order_times[0] > timedelta(minutes=1):
            self._order_times.popleft()
        if len(self._order_times) + n > self.cfg.max_orders_per_minute:
            return False
        self._order_times.extend([now] * n)
        return True

    def submit_decision(
        self, decision: RiskDecision, now: datetime, meta: Mapping[str, object] | None = None
    ) -> list[Order] | Proposal | None:
        """Punto único de entrada de nuevas operaciones."""
        if not decision.approved or decision.qty < 1:
            return None
        meta = dict(meta or {})
        if self.mode is RunMode.ANALYSIS:
            log.info("ANALYSIS (no se envía): %s", decision.summary())
            return None
        if self.mode is RunMode.LIVE_PROPOSAL:
            pid = next_id("P")
            prop = Proposal(pid, decision, now, now + timedelta(seconds=self.cfg.proposal_ttl_seconds), meta)
            self.proposals[pid] = prop
            self.on_alert("INFO", f"Propuesta {pid}: {decision.summary()}")
            return prop
        return self._send_bracket(decision, now, meta)

    def confirm(
        self, proposal_id: str, now: datetime, account: AccountState, marks: Mapping[str, float]
    ) -> list[Order] | None:
        """Confirma una propuesta. Se vuelve a pasar por el RiskEngine con el estado ACTUAL."""
        prop = self.proposals.get(proposal_id)
        if prop is None or prop.status != "PENDING":
            return None
        if now > prop.expires:
            prop.status = "EXPIRED"
            return None
        prop.status = "CONFIRMED"  # sale de working_entry_qty antes de re-evaluar
        intent = prop.decision.intent
        fresh = self.risk.evaluate(
            replace(intent, ts=now), account, self.position_risks(marks), self.working_entry_qty()
        )
        if not fresh.approved:
            prop.status = "REJECTED"
            self.on_alert("WARNING", f"Propuesta {proposal_id} vetada al confirmar: {fresh.summary()}")
            return None
        return self._send_bracket(fresh, now, prop.meta)

    def reject(self, proposal_id: str) -> None:
        if proposal_id in self.proposals:
            self.proposals[proposal_id].status = "REJECTED"

    def expire_proposals(self, now: datetime) -> None:
        for p in self.proposals.values():
            if p.status == "PENDING" and now > p.expires:
                p.status = "EXPIRED"

    def _send_bracket(self, d: RiskDecision, now: datetime, meta: dict[str, object]) -> list[Order] | None:
        it = d.intent
        spec = self.specs[it.root]
        if self.mode is RunMode.LIVE_AUTO and not self._rate_ok(now, 3):
            self.risk.report_execution_anomaly(self.risk.account_cal.trade_date(now), "límite de órdenes/minuto")
            self.on_alert("CRITICAL", "Limitador de órdenes activado: posible bucle. Día detenido.")
            return None
        if it.entry_type is OrderType.LIMIT:
            off = self.cfg.limit_offset_ticks * spec.tick_size * int(it.side)
            entry = Order(it.root, it.contract, it.side, d.qty, OrderType.LIMIT, "entry", now,
                          limit_price=spec.round_price(it.entry_price - off), expected_price=it.entry_price)
        else:
            entry = Order(it.root, it.contract, it.side, d.qty, OrderType.MARKET, "entry", now,
                          expected_price=it.entry_price)
        oco = next_id("G")
        stop = Order(it.root, it.contract, it.side.opposite, d.qty, OrderType.STOP, "stop", now,
                     stop_price=it.stop_price, parent_id=entry.id, oco_group=oco, status=OrderStatus.HELD)
        orders = [entry, stop]
        target = None
        if it.target_price is not None:
            target = Order(it.root, it.contract, it.side.opposite, d.qty, OrderType.LIMIT, "target", now,
                           limit_price=it.target_price, parent_id=entry.id, oco_group=oco,
                           status=OrderStatus.HELD)
            orders.append(target)
        for o in orders:
            self.broker.submit(o)
            if o.status is OrderStatus.REJECTED:
                for x in orders:
                    self.broker.cancel(x.id)
                self.on_alert("ERROR", f"Orden rechazada {o.id}: {o.reject_reason}")
                return None
        self._brackets[it.root] = _Bracket(
            entry.id, stop.id, target.id if target else None,
            {**meta, "decision": d, "stop": it.stop_price, "target": it.target_price},
        )
        return orders

    # ------------------------------------------------------------------ #
    # Fills
    # ------------------------------------------------------------------ #
    def on_fills(self, fills: Iterable[Fill], account: AccountState) -> list[TradeRecord]:
        closed: list[TradeRecord] = []
        for f in fills:
            spec = self.specs[f.root]
            pos = self.positions.setdefault(f.root, Position(f.root, f.contract))
            if pos.qty == 0:
                pos.contract = f.contract
            realized, opened = pos.apply_fill(f.side, f.qty, f.price, spec.multiplier)
            account.on_fill(realized, f.commission, opened)
            self._track_slippage(f, account)
            br = self._brackets.get(f.root)

            if opened:
                d: RiskDecision | None = br.meta.get("decision") if br else None  # type: ignore[assignment]
                pos.entry_ts, pos.bars_held = f.ts, 0
                pos.stop_price = float(br.meta["stop"]) if br else None  # type: ignore[arg-type]
                pos.target_price = br.meta.get("target") if br else None  # type: ignore[assignment]
                pos.initial_stop = pos.stop_price
                pos.best_price = pos.worst_price = f.price
                pos.meta["bracket"] = br.entry_id if br else None
                tid = next_id("T")
                pos.trade_id = tid
                self._open_trades[f.root] = TradeRecord(
                    tid, f.root, f.contract, f.side, 0, f.ts, f.price,
                    initial_risk_usd=0.0,
                    regime=str(br.meta.get("regime", "")) if br else "",
                    confidence=float(br.meta.get("confidence", 0.0)) if br else 0.0,  # type: ignore[arg-type]
                    explanation=str(br.meta.get("explanation", "")) if br else "",
                )
                if d is not None:
                    self._open_trades[f.root].initial_risk_usd = d.risk_per_contract
            tr = self._open_trades.get(f.root)
            if tr is not None:
                tr.commissions += f.commission
                tr.gross_pnl += realized
                if f.tag == "entry":
                    tr.qty += f.qty
                    tr.entry_price = pos.avg_price
            if f.tag == "entry" and br is not None:
                n = abs(pos.qty)
                if br.stop_id:
                    self.broker.set_open_qty(br.stop_id, n, activate=True)
                if br.target_id:
                    self.broker.set_open_qty(br.target_id, n, activate=True)
            elif f.tag != "entry":
                self._sync_exit_orders(f.root)

            if pos.qty == 0 and tr is not None:
                tr.exit_ts, tr.exit_price = f.ts, f.price
                tr.exit_reason = tr.exit_reason or f.tag
                tr.bars_held = pos.bars_held
                if tr.initial_risk_usd and tr.qty:
                    tr.initial_risk_usd = tr.initial_risk_usd * tr.qty
                account.on_trade_closed(tr.net_pnl, f.ts)
                self.trades.append(tr)
                closed.append(tr)
                del self._open_trades[f.root]
                old = pos.meta.get("bracket")
                for o in self.broker.open_orders(f.root):
                    if o.parent_id is not None and o.parent_id == old:
                        self.broker.cancel(o.id)
                if br is not None and br.entry_id == old:
                    self._brackets.pop(f.root, None)
                pos.stop_price = pos.target_price = None
                pos.meta.pop("bracket", None)
        return closed

    def _sync_exit_orders(self, root: str) -> None:
        """Ajusta stop/target de la posición vigente a su tamaño real (tras salidas parciales).

        Sólo toca las órdenes del bracket que abrió ESTA posición: durante un roll
        conviven las órdenes del contrato nuevo, que no deben alterarse.
        """
        pos = self.positions.get(root)
        n = abs(pos.qty) if pos else 0
        owner = pos.meta.get("bracket") if pos else None
        for o in self.broker.open_orders(root):
            if o.tag in ("stop", "target") and o.parent_id == owner:
                self.broker.set_open_qty(o.id, n)

    def _track_slippage(self, f: Fill, account: AccountState) -> None:
        self._slippage.append(f.slippage_ticks)
        lim = self.risk.limits.max_slippage_ticks_alert
        if f.slippage_ticks > lim:
            self.on_alert("WARNING", f"Slippage {f.slippage_ticks:.1f} ticks en {f.root} ({f.tag})")
        if len(self._slippage) >= 10:
            avg = sum(list(self._slippage)[-10:]) / 10
            if avg > lim:
                td = self.risk.account_cal.trade_date(f.ts)
                self.risk.report_execution_anomaly(td, f"slippage medio {avg:.1f} ticks")

    def _cancel_root(self, root: str, tags: tuple[str, ...] | None = None) -> None:
        for o in self.broker.open_orders(root):
            if tags is None or o.tag in tags:
                self.broker.cancel(o.id)

    # ------------------------------------------------------------------ #
    # Gestión de posiciones
    # ------------------------------------------------------------------ #
    def flatten(self, roots: Iterable[str] | None, reason: str, now: datetime) -> list[Order]:
        """Cancela órdenes y cierra a mercado. Siempre permitido (reduce riesgo)."""
        out: list[Order] = []
        targets = set(roots) if roots is not None else set(self.positions) | {
            o.root for o in self.broker.open_orders()
        }
        for root in targets:
            self._cancel_root(root)
            for p in list(self.proposals.values()):
                if p.status == "PENDING" and p.decision.intent.root == root:
                    p.status = "REJECTED"
            pos = self.positions.get(root)
            if pos and pos.qty != 0:
                side = Side.SHORT if pos.qty > 0 else Side.LONG
                o = Order(root, pos.contract, side, abs(pos.qty), OrderType.MARKET, "flatten", now)
                self.broker.submit(o)
                out.append(o)
                tr = self._open_trades.get(root)
                if tr is not None and not tr.exit_reason:
                    tr.exit_reason = reason
        return out

    def on_bar_end(self, root: str, close: float, high: float, low: float, atr: float, now: datetime) -> None:
        """Mantenimiento por barra: timeouts de entradas, MFE/MAE, breakeven/trailing, time stop."""
        for o in self.broker.open_orders(root):
            if o.tag == "entry":
                o.bars_alive += 1
                if o.bars_alive >= self.cfg.entry_timeout_bars and o.type is OrderType.LIMIT:
                    self.broker.cancel(o.id)
                    if o.filled_qty == 0:
                        self._cancel_root(root)
                        self._brackets.pop(root, None)
        pos = self.position(root)
        if pos is None:
            return
        spec = self.specs[root]
        pos.bars_held += 1
        long = pos.qty > 0
        pos.best_price = max(pos.best_price or high, high) if long else min(pos.best_price or low, low)
        pos.worst_price = min(pos.worst_price or low, low) if long else max(pos.worst_price or high, high)
        tr = self._open_trades.get(root)
        if tr is not None:
            fav = (pos.best_price - pos.avg_price) * (1 if long else -1)
            adv = (pos.worst_price - pos.avg_price) * (1 if long else -1)
            tr.mfe_usd = max(tr.mfe_usd, spec.points_to_usd(fav, abs(pos.qty)))
            tr.mae_usd = min(tr.mae_usd, spec.points_to_usd(adv, abs(pos.qty)))

        if pos.bars_held >= self.pcfg.max_holding_bars:
            self.flatten([root], "time stop", now)
            return
        if pos.initial_stop is None or pos.stop_price is None or not math.isfinite(atr) or atr <= 0:
            return
        r_pts = abs(pos.avg_price - pos.initial_stop)
        if r_pts <= 0:
            return
        sgn = 1 if long else -1
        gain_r = (close - pos.avg_price) * sgn / r_pts
        new_stop = pos.stop_price
        if gain_r >= self.pcfg.breakeven_at_r:
            be = pos.avg_price + sgn * 2 * spec.tick_size  # cubre comisiones
            new_stop = max(new_stop, be) if long else min(new_stop, be)
        if gain_r >= self.pcfg.trail_after_r:
            tr_stop = close - sgn * self.pcfg.trail_atr * atr
            new_stop = max(new_stop, tr_stop) if long else min(new_stop, tr_stop)
        new_stop = spec.round_stop(new_stop, long)
        # nunca dejar el stop al otro lado del precio actual
        if (close - new_stop) * sgn <= spec.tick_size:
            return
        if (new_stop - pos.stop_price) * sgn > 0:
            br = self._brackets.get(root)
            if br and self.broker.modify_stop(br.stop_id, new_stop):
                pos.stop_price = new_stop

    def roll_position(
        self, root: str, new_contract: str, price_offset: float, now: datetime, policy: str = "flatten"
    ) -> list[Order]:
        """Rollover de una posición abierta.

        * ``flatten``: cierra a mercado (recomendado en cuentas de fondeo intradía).
        * ``roll``: cierra el contrato viejo y abre la misma cantidad en el nuevo,
          desplazando stop/target por el spread de calendario (``price_offset`` =
          precio_nuevo - precio_viejo). En serie continua ajustada el offset es 0.
        """
        pos = self.position(root)
        if pos is None or pos.contract == new_contract:
            return []
        if policy == "flatten":
            return self.flatten([root], f"rollover {pos.contract}->{new_contract}", now)
        qty, side = abs(pos.qty), (Side.LONG if pos.qty > 0 else Side.SHORT)
        stop = (pos.stop_price + price_offset) if pos.stop_price is not None else None
        target = (pos.target_price + price_offset) if pos.target_price is not None else None
        out = self.flatten([root], f"roll {pos.contract}->{new_contract}", now)
        entry = Order(root, new_contract, side, qty, OrderType.MARKET, "entry", now)
        oco = next_id("G")
        orders = [entry]
        if stop is not None:
            orders.append(Order(root, new_contract, side.opposite, qty, OrderType.STOP, "stop", now,
                                stop_price=stop, parent_id=entry.id, oco_group=oco, status=OrderStatus.HELD))
        if target is not None:
            orders.append(Order(root, new_contract, side.opposite, qty, OrderType.LIMIT, "target", now,
                                limit_price=target, parent_id=entry.id, oco_group=oco, status=OrderStatus.HELD))
        for o in orders:
            self.broker.submit(o)
        self._brackets[root] = _Bracket(
            entry.id, orders[1].id if stop is not None else "", orders[2].id if target is not None else None,
            {"stop": stop, "target": target, "explanation": "roll"},
        )
        return out + orders
