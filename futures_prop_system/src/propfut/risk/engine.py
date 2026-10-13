"""Risk & Prop Firm Compliance Engine — **veto absoluto** sobre cualquier operación.

Ningún componente puede enviar una orden de entrada sin un :class:`RiskDecision`
aprobado. El motor:

1. Verifica el estado de la cuenta (ruptura, halt diario, kill switch).
2. Verifica horario (RTH, flatten de la firma, ventanas previas al cierre), roll y noticias.
3. Verifica límites diarios (soft stop, profit lock/consistencia, nº trades, rachas, cooldown).
4. Valida el stop (existe, lado correcto, distancia mínima) y el ratio R:R.
5. Dimensiona en **contratos enteros** con el mínimo de varios presupuestos:
   riesgo fijo por trade, fracción del colchón trailing, fracción del colchón diario,
   todo escalado por la utilización del drawdown y por la convicción de la policy.
6. Aplica límites de contratos (en minis), posiciones abiertas, margen y
   **riesgo de cartera con correlaciones** (sqrt(wᵀ C w)).
7. Comprueba el peor caso: si TODAS las posiciones (incluida la nueva) tocan su
   stop con slippage, no se puede romper ni el límite diario interno ni el de la
   firma ni el umbral trailing.

Además vigila circuit breakers en cada barra/tick (:meth:`check_circuit_breakers`).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum

import numpy as np

from propfut.contracts.specs import ContractSpec
from propfut.core.config import InternalRiskConfig, PropFirmRules
from propfut.core.sessions import SessionCalendar
from propfut.core.types import OrderType, Side
from propfut.data.news import Impact, NewsCalendar
from propfut.risk.account import AccountState


@dataclass(frozen=True)
class TradeIntent:
    """Propuesta de operación (antes de dimensionar)."""

    root: str
    contract: str
    side: Side
    entry_price: float
    stop_price: float
    target_price: float | None
    ts: datetime
    size_fraction: float = 1.0  # convicción de la policy en [0, 1]
    confidence: float = 0.0
    entry_type: OrderType = OrderType.MARKET
    reason: str = ""
    regime: str = ""


@dataclass(frozen=True)
class PositionRisk:
    """Vista de una posición abierta para el cálculo de riesgo."""

    root: str
    contract: str
    qty: int  # con signo
    avg_price: float
    stop_price: float | None
    mark_price: float


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    qty: int
    intent: TradeIntent
    reasons: tuple[str, ...]
    checks: Mapping[str, object] = field(default_factory=dict)
    risk_per_contract: float = 0.0
    risk_usd: float = 0.0

    def summary(self) -> str:
        head = f"APROBADA {self.qty}x" if self.approved else "VETADA"
        return f"{head} {self.intent.side.name} {self.intent.contract} | " + "; ".join(self.reasons)


class RiskActionType(str, Enum):
    BLOCK_ENTRIES = "BLOCK_ENTRIES"
    FLATTEN_ALL = "FLATTEN_ALL"
    FLATTEN_ROOTS = "FLATTEN_ROOTS"
    HALT_DAY = "HALT_DAY"
    HALT_ACCOUNT = "HALT_ACCOUNT"


@dataclass(frozen=True)
class RiskAction:
    kind: RiskActionType
    reason: str
    roots: tuple[str, ...] = ()


class CorrelationModel:
    """Matriz de correlación entre raíces: pares explícitos > mismo grupo > 0."""

    def __init__(
        self,
        specs: Mapping[str, ContractSpec],
        pairs: Mapping[str, float] | None = None,
        same_group: float = 0.8,
    ) -> None:
        self.specs = specs
        self.same_group = same_group
        self.pairs: dict[frozenset[str], float] = {}
        for k, v in (pairs or {}).items():
            a, b = (s.strip() for s in k.split("-"))
            self.pairs[frozenset((a, b))] = float(v)

    def corr(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        key = frozenset((a, b))
        if key in self.pairs:
            return self.pairs[key]
        sa, sb = self.specs.get(a), self.specs.get(b)
        # una micro y su mini (MES/ES) comparten subyacente
        if sa and sb and sa.cfg.correlation_group == sb.cfg.correlation_group:
            return self.same_group
        return 0.0

    def portfolio_risk(self, signed_risk: Mapping[str, float]) -> float:
        roots = [r for r, v in signed_risk.items() if v != 0]
        if not roots:
            return 0.0
        w = np.array([signed_risk[r] for r in roots])
        c = np.array([[self.corr(a, b) for b in roots] for a in roots])
        return float(math.sqrt(max(0.0, w @ c @ w)))


class RiskEngine:
    def __init__(
        self,
        rules: PropFirmRules,
        limits: InternalRiskConfig,
        specs: Mapping[str, ContractSpec],
        sessions: Mapping[str, SessionCalendar],
        news: NewsCalendar | None = None,
        roll_guard: Callable[[str, date], bool] | None = None,
    ) -> None:
        self.rules = rules
        self.limits = limits
        self.specs = specs
        self.sessions = sessions
        self.news = news or NewsCalendar()
        self.roll_guard = roll_guard
        self.account_cal = SessionCalendar(rules.timezone, rules.day_reset_time)
        self.corr = CorrelationModel(specs, limits.correlations, limits.same_group_default_correlation)
        self.kill_switch = False
        self.kill_reason = ""
        self.halted_date: date | None = None
        self.halt_reason = ""

    # ------------------------------------------------------------------ #
    # Estado
    # ------------------------------------------------------------------ #
    def engage_kill_switch(self, reason: str) -> None:
        self.kill_switch = True
        self.kill_reason = reason

    def halt_day(self, trade_date: date, reason: str) -> None:
        if self.halted_date != trade_date:
            self.halted_date = trade_date
            self.halt_reason = reason

    def is_halted(self, trade_date: date) -> bool:
        return self.halted_date == trade_date

    def report_execution_anomaly(self, trade_date: date, reason: str) -> None:
        """Llamado por el ExecutionManager (slippage anómalo, rechazos, desconexión...)."""
        self.halt_day(trade_date, f"Anomalía de ejecución: {reason}")

    # ------------------------------------------------------------------ #
    # Utilidades de riesgo
    # ------------------------------------------------------------------ #
    def per_contract_risk(self, spec: ContractSpec, entry: float, stop: float) -> float:
        """USD perdidos por contrato si salta el stop, incluyendo slippage y comisiones."""
        lim = self.limits
        dist = abs(entry - stop) * spec.multiplier
        slip = (lim.stop_slippage_buffer_ticks + spec.cfg.slippage_ticks) * spec.tick_value
        return dist + slip + 2 * spec.cfg.commission_per_side

    def position_loss_to_stop(self, p: PositionRisk) -> float:
        """Pérdida desde el precio actual hasta el stop (peor caso). Sin stop => riesgo infinito."""
        spec = self.specs[p.root]
        if p.stop_price is None:
            return math.inf
        side = 1 if p.qty > 0 else -1
        move = (p.mark_price - p.stop_price) * side
        slip = (self.limits.stop_slippage_buffer_ticks + spec.cfg.slippage_ticks) * spec.tick_value
        return max(0.0, move * spec.multiplier * abs(p.qty)) + slip * abs(p.qty) + spec.cfg.commission_per_side * abs(p.qty)

    def dd_multiplier(self, account: AccountState) -> float:
        u = account.dd_utilization
        m = 1.0
        for tier in self.limits.drawdown_tiers:
            if u >= tier.utilization:
                m = tier.risk_multiplier
        return m

    def daily_profit_cap(self) -> float | None:
        caps: list[float] = []
        if self.limits.daily_profit_lock_usd is not None:
            caps.append(self.limits.daily_profit_lock_usd)
        share = self.rules.consistency_max_day_share
        if share is not None and self.rules.profit_target > 0:
            caps.append(share * self.rules.profit_target * 0.9)  # margen del 10 %
        return min(caps) if caps else None

    def _in_flatten_window(self, now: datetime) -> bool:
        lim, r = self.limits, self.rules
        start = (datetime.combine(date(2000, 1, 1), r.flatten_time) - timedelta(minutes=lim.flatten_buffer_minutes)).time()
        return self.account_cal.is_between(now, start, r.day_reset_time)

    def _news_blackout(self, root: str, now: datetime) -> str | None:
        lim, r = self.limits, self.rules
        before = max(lim.news_blackout_minutes_before, r.news_blackout_minutes_before if r.news_restricted else 0)
        after = max(lim.news_blackout_minutes_after, r.news_blackout_minutes_after if r.news_restricted else 0)
        ev = self.news.blackout(root, now, before, after, Impact.HIGH)
        return f"Blackout de noticias: {ev.title} ({ev.ts:%H:%M} UTC)" if ev else None

    # ------------------------------------------------------------------ #
    # Evaluación de una propuesta
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        intent: TradeIntent,
        account: AccountState,
        positions: Sequence[PositionRisk],
        working_entry_qty: Mapping[str, int] | None = None,
    ) -> RiskDecision:
        working_entry_qty = working_entry_qty or {}
        checks: dict[str, object] = {}
        now = intent.ts

        def veto(reason: str) -> RiskDecision:
            return RiskDecision(False, 0, intent, (reason,), checks)

        lim, rules = self.limits, self.rules
        spec = self.specs.get(intent.root)
        if spec is None:
            return veto(f"Instrumento {intent.root} sin especificación")
        if rules.allowed_roots and intent.root not in rules.allowed_roots:
            return veto(f"{intent.root} no permitido por la prop firm")

        # 1. estado de la cuenta
        if account.breached:
            return veto(f"Cuenta rota: {account.breach_reason}")
        if self.kill_switch:
            return veto(f"Kill switch activo: {self.kill_reason}")
        td = self.account_cal.trade_date(now)
        if self.is_halted(td):
            return veto(f"Día detenido: {self.halt_reason}")
        if account.day_locked:
            return veto(account.day_lock_reason)

        # 2. horario, roll, noticias
        session = self.sessions.get(intent.root, self.account_cal)
        if lim.rth_only_entries and not session.is_rth(now):
            return veto("Fuera de RTH (rth_only_entries)")
        if lim.no_entry_minutes_after_open > 0 and session.is_rth(now):
            since_open = -session.minutes_until(now, session.rth_open)
            if since_open < lim.no_entry_minutes_after_open:
                return veto(f"Primeros {lim.no_entry_minutes_after_open} min de RTH (ruido de apertura)")
        if self._in_flatten_window(now):
            return veto("Dentro de la ventana de cierre obligatorio de la firma")
        mins_to_flat = self.account_cal.minutes_until(now, rules.flatten_time)
        checks["minutes_to_flatten"] = round(mins_to_flat, 1)
        if 0 <= mins_to_flat < lim.no_entry_minutes_before_flatten:
            return veto(f"A {mins_to_flat:.0f} min del cierre obligatorio (mín. {lim.no_entry_minutes_before_flatten})")
        if self.roll_guard is not None and not self.roll_guard(intent.root, td):
            return veto("Entradas bloqueadas por proximidad del rollover")
        nb = self._news_blackout(intent.root, now)
        if nb:
            return veto(nb)

        # 3. límites diarios
        dp = account.daily_pnl
        checks["daily_pnl"] = round(dp, 2)
        if dp <= -lim.daily_loss_soft_stop_usd:
            return veto(f"Soft stop diario: {dp:.2f} <= -{lim.daily_loss_soft_stop_usd:.2f}")
        cap = self.daily_profit_cap()
        if cap is not None and dp >= cap:
            return veto(f"Profit lock diario/consistencia alcanzado ({dp:.2f} >= {cap:.2f})")
        if account.trades_today >= lim.max_trades_per_day:
            return veto(f"Máximo de operaciones diarias ({lim.max_trades_per_day})")
        if account.consecutive_losses >= lim.max_consecutive_losses:
            return veto(f"{account.consecutive_losses} pérdidas consecutivas: pausa del día")
        if account.last_loss_ts is not None and lim.cooldown_minutes_after_loss > 0:
            since = (now - account.last_loss_ts).total_seconds() / 60
            if since < lim.cooldown_minutes_after_loss:
                return veto(f"Cooldown tras pérdida ({since:.0f}/{lim.cooldown_minutes_after_loss} min)")

        # 4. validación del stop y R:R
        side = intent.side
        entry = spec.round_price(intent.entry_price)
        stop = spec.round_stop(intent.stop_price, side is Side.LONG)
        if (entry - stop) * side <= 0:
            return veto(f"Stop en el lado incorrecto (entry {entry}, stop {stop})")
        stop_ticks = abs(entry - stop) / spec.tick_size
        if stop_ticks < lim.min_stop_ticks:
            return veto(f"Stop demasiado cercano ({stop_ticks:.0f} ticks < {lim.min_stop_ticks})")
        target = intent.target_price
        if target is not None:
            target = spec.round_price(target)
            if (target - entry) * side <= 0:
                return veto("Target en el lado incorrecto")
            rr = abs(target - entry) / abs(entry - stop)
            checks["reward_risk"] = round(rr, 2)
            if rr < lim.min_reward_risk:
                return veto(f"R:R {rr:.2f} < mínimo {lim.min_reward_risk}")
        if any(p.root == intent.root and p.qty != 0 for p in positions) or working_entry_qty.get(intent.root):
            return veto(f"Ya existe posición/orden en {intent.root} (sin piramidación)")

        # 5. sizing
        per_c = self.per_contract_risk(spec, entry, stop)
        open_loss = sum(self.position_loss_to_stop(p) for p in positions if p.qty != 0)
        if math.isinf(open_loss):
            return veto("Hay posiciones abiertas sin stop: prohibido añadir riesgo")
        room_trailing = account.trailing_room - open_loss - lim.min_trailing_room_usd
        room_daily_int = lim.daily_loss_flatten_usd + dp - open_loss
        room_daily_firm = (
            rules.daily_loss_limit + dp - open_loss if rules.daily_loss_limit is not None else math.inf
        )
        dd_mult = self.dd_multiplier(account)
        frac = max(0.0, min(1.0, intent.size_fraction))
        budget = min(
            lim.max_risk_per_trade_usd,
            lim.max_risk_fraction_of_dd_room * max(0.0, room_trailing),
            lim.max_risk_fraction_of_daily_room * max(0.0, room_daily_int),
        ) * dd_mult * frac
        checks.update(
            per_contract_risk=round(per_c, 2), open_loss_to_stops=round(open_loss, 2),
            room_trailing=round(room_trailing, 2), room_daily_internal=round(room_daily_int, 2),
            room_daily_firm=round(room_daily_firm, 2) if math.isfinite(room_daily_firm) else None,
            dd_utilization=round(account.dd_utilization, 3), dd_multiplier=dd_mult,
            size_fraction=round(frac, 3), budget=round(budget, 2),
        )
        qty = int(math.floor(budget / per_c)) if per_c > 0 else 0
        if qty < 1:
            return veto(
                f"Presupuesto {budget:.0f} USD < riesgo de 1 contrato {per_c:.0f} USD "
                f"(usa micros o un stop más corto)"
            )
        reasons: list[str] = []

        # 6. límites de contratos / posiciones / margen / correlación
        root_cap = lim.max_contracts_per_root.get(intent.root)
        if root_cap is not None and qty > root_cap:
            qty = root_cap
            reasons.append(f"cap por raíz {root_cap}")
        max_minis = min(rules.max_contracts_mini_equiv, lim.max_mini_equiv_contracts)
        used_minis = sum(self.specs[p.root].mini_equivalent(p.qty) for p in positions) + sum(
            self.specs[r].mini_equivalent(q) for r, q in working_entry_qty.items() if r in self.specs
        )
        allowed = int(math.floor((max_minis - used_minis) / spec.cfg.mini_equivalent + 1e-9))
        if allowed < 1:
            return veto(f"Límite de contratos alcanzado ({used_minis:.1f}/{max_minis} minis)")
        if qty > allowed:
            qty = allowed
            reasons.append(f"limitado por máx. contratos ({max_minis} minis)")
        open_roots = {p.root for p in positions if p.qty != 0} | {r for r, q in working_entry_qty.items() if q}
        if len(open_roots) >= lim.max_open_positions:
            return veto(f"Máximo de posiciones abiertas ({lim.max_open_positions})")
        used_margin = sum(self.specs[p.root].margin(p.qty) for p in positions)
        max_margin = lim.max_margin_utilization * account.equity
        m_allowed = int((max_margin - used_margin) // max(spec.cfg.day_trade_margin, 1e-9))
        if m_allowed < 1:
            return veto("Margen insuficiente")
        if qty > m_allowed:
            qty = m_allowed
            reasons.append("limitado por margen")

        signed: dict[str, float] = {}
        for p in positions:
            if p.qty:
                signed[p.root] = signed.get(p.root, 0.0) + math.copysign(self.position_loss_to_stop(p), p.qty)
        reduced_by_corr = False
        while qty >= 1:
            trial = dict(signed)
            trial[intent.root] = trial.get(intent.root, 0.0) + side * qty * per_c
            port = self.corr.portfolio_risk(trial)
            if port <= lim.max_portfolio_risk_usd:
                checks["portfolio_risk"] = round(port, 2)
                break
            qty -= 1
            reduced_by_corr = True
        if reduced_by_corr and qty >= 1:
            reasons.append("reducido por riesgo de cartera correlacionado")
        if qty < 1:
            return veto(f"Riesgo de cartera correlacionado > {lim.max_portfolio_risk_usd:.0f} USD")

        # 7. peor caso
        worst = open_loss + qty * per_c
        hard_room = min(account.trailing_room, room_daily_firm + open_loss, lim.daily_loss_flatten_usd + dp)
        while qty >= 1 and worst >= hard_room:
            qty -= 1
            worst = open_loss + qty * per_c
        if qty < 1:
            return veto("El peor caso (todos los stops) rompería un límite duro")
        checks["worst_case_loss"] = round(worst, 2)

        final = replace(intent, entry_price=entry, stop_price=stop, target_price=target)
        reasons.insert(0, f"{qty} contrato(s), riesgo {qty * per_c:.0f} USD ({per_c:.0f}/c)")
        return RiskDecision(True, qty, final, tuple(reasons), checks, per_c, qty * per_c)

    # ------------------------------------------------------------------ #
    # Circuit breakers (cada barra / tick)
    # ------------------------------------------------------------------ #
    def check_circuit_breakers(
        self,
        account: AccountState,
        positions: Sequence[PositionRisk],
        now: datetime,
        horizon: timedelta = timedelta(0),
    ) -> list[RiskAction]:
        """``now`` = instante de decisión (cierre de barra); ``horizon`` = tiempo hasta la
        siguiente oportunidad de actuar (duración de la barra). El flatten horario se
        dispara si la ventana de cierre empieza antes de esa siguiente oportunidad."""
        lim, rules = self.limits, self.rules
        acts: list[RiskAction] = []
        td = self.account_cal.trade_date(now)
        has_pos = any(p.qty != 0 for p in positions)

        if account.breached:
            return [RiskAction(RiskActionType.FLATTEN_ALL, account.breach_reason),
                    RiskAction(RiskActionType.HALT_ACCOUNT, account.breach_reason)]
        if self.kill_switch:
            return [RiskAction(RiskActionType.FLATTEN_ALL, self.kill_reason),
                    RiskAction(RiskActionType.HALT_ACCOUNT, self.kill_reason)]
        if account.day_locked:
            self.halt_day(td, account.day_lock_reason)
            acts.append(RiskAction(RiskActionType.FLATTEN_ALL, account.day_lock_reason))
        flat_due = self._in_flatten_window(now) or self._in_flatten_window(now + horizon)
        if rules.no_overnight and flat_due and has_pos:
            acts.append(RiskAction(RiskActionType.FLATTEN_ALL, "Hora de cierre obligatorio de la firma"))

        dp = account.daily_pnl
        if dp <= -lim.daily_loss_flatten_usd:
            reason = f"Pérdida diaria {dp:.2f} <= -{lim.daily_loss_flatten_usd:.2f}: cerrar todo"
            self.halt_day(td, reason)
            acts.append(RiskAction(RiskActionType.FLATTEN_ALL, reason))
        elif dp <= -lim.daily_loss_soft_stop_usd:
            self.halt_day(td, f"Soft stop diario ({dp:.2f})")
        cap = self.daily_profit_cap()
        if cap is not None and dp >= cap:
            self.halt_day(td, f"Profit lock diario ({dp:.2f} >= {cap:.2f})")
        if account.consecutive_losses >= lim.max_consecutive_losses:
            self.halt_day(td, f"{account.consecutive_losses} pérdidas consecutivas")

        open_loss = sum(self.position_loss_to_stop(p) for p in positions if p.qty != 0)
        if math.isinf(open_loss):
            acts.append(RiskAction(RiskActionType.FLATTEN_ALL, "Posición sin stop detectada"))
        else:
            room_after = account.trailing_room - open_loss
            if room_after < lim.min_trailing_room_usd:
                self.halt_day(td, f"Colchón trailing bajo ({account.trailing_room:.0f} USD)")
            if account.trailing_room < 0.5 * lim.min_trailing_room_usd and has_pos:
                acts.append(RiskAction(RiskActionType.FLATTEN_ALL, "Colchón trailing crítico"))

        if lim.flatten_before_high_impact_news and has_pos:
            roots = tuple(
                sorted({p.root for p in positions if p.qty and self.news.blackout(
                    p.root, now, lim.news_blackout_minutes_before, 0, Impact.HIGH)})
            )
            if roots:
                acts.append(RiskAction(RiskActionType.FLATTEN_ROOTS, "Noticia de alto impacto inminente", roots))
        if self.is_halted(td):
            acts.append(RiskAction(RiskActionType.HALT_DAY, self.halt_reason))
        return acts

    def snapshot(self, now: datetime) -> dict[str, object]:
        td = self.account_cal.trade_date(now)
        return {
            "kill_switch": self.kill_switch,
            "kill_reason": self.kill_reason,
            "halted_today": self.is_halted(td),
            "halt_reason": self.halt_reason if self.is_halted(td) else "",
            "daily_profit_cap": self.daily_profit_cap(),
        }
