"""Estado de la cuenta de fondeo y replicación exacta de las reglas de drawdown.

Modelos de trailing soportados (``PropFirmRules.trailing_mode``):

* ``static``      umbral fijo = balance inicial - max_loss.
* ``intraday``    el umbral sigue al **máximo de equity** (incluye PnL no realizado
                  en su mejor momento). Es el más peligroso: un trade que llega a
                  +800 y vuelve a 0 ha consumido 800 de colchón.
* ``end_of_day``  el umbral sólo se actualiza con el balance de cierre de sesión.

``trailing_lock_level``: cuando ``hwm - max_loss`` alcanza ese nivel, el umbral
deja de subir (p.ej. muchas firmas lo congelan en el balance inicial).

Para el backtest se usa la convención **pesimista** dentro de cada barra: primero
se actualiza el máximo con el extremo favorable y después se evalúa la ruptura
con el extremo adverso.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from propfut.core.config import PropFirmRules, TrailingMode


@dataclass
class DayRecord:
    trade_date: date
    start_balance: float
    end_balance: float = 0.0
    pnl: float = 0.0
    min_equity: float = 0.0
    max_equity: float = 0.0
    trades: int = 0
    commissions: float = 0.0
    threshold_eod: float = 0.0


@dataclass
class AccountState:
    rules: PropFirmRules
    balance: float = field(init=False)
    open_pnl: float = 0.0
    hwm: float = field(init=False)
    threshold: float = field(init=False)
    trade_date: date | None = None
    day_start_balance: float = field(init=False)
    day_min_equity: float = field(init=False)
    day_max_equity: float = field(init=False)
    trades_today: int = 0
    consecutive_losses: int = 0
    last_loss_ts: datetime | None = None
    breached: bool = False
    breach_reason: str = ""
    day_locked: bool = False
    day_lock_reason: str = ""
    total_commissions: float = 0.0
    history: list[DayRecord] = field(default_factory=list)
    trade_pnls: list[float] = field(default_factory=list)
    _today: DayRecord | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        r = self.rules
        self.balance = r.account_size
        self.hwm = r.account_size
        self.threshold = r.initial_threshold
        self.day_start_balance = self.balance
        self.day_min_equity = self.day_max_equity = self.balance

    # ------------------------------------------------------------------ #
    @property
    def equity(self) -> float:
        return self.balance + self.open_pnl

    @property
    def daily_pnl(self) -> float:
        return self.equity - self.day_start_balance

    @property
    def trailing_room(self) -> float:
        """USD hasta el umbral de liquidación (max loss)."""
        return self.equity - self.threshold

    @property
    def dd_utilization(self) -> float:
        """0 = colchón intacto, 1 = en el umbral."""
        return min(1.0, max(0.0, 1.0 - self.trailing_room / self.rules.max_loss))

    @property
    def total_pnl(self) -> float:
        return self.balance - self.rules.account_size

    @property
    def trading_days(self) -> int:
        return sum(1 for d in self.history if d.trades > 0) + (
            1 if self._today and self._today.trades > 0 else 0
        )

    # ------------------------------------------------------------------ #
    def _raise_threshold(self, level: float) -> None:
        new = level - self.rules.max_loss
        lock = self.rules.trailing_lock_level
        if lock is not None:
            new = min(new, lock)
        if new > self.threshold:
            self.threshold = new

    def start_day(self, trade_date: date) -> None:
        """Cierra el día anterior (trailing EOD) y abre uno nuevo."""
        if self.trade_date == trade_date:
            return
        if self._today is not None:
            self._close_day()
        self.trade_date = trade_date
        self.day_start_balance = self.equity
        self.day_min_equity = self.day_max_equity = self.equity
        self.trades_today = 0
        self.consecutive_losses = 0
        self.day_locked = False
        self.day_lock_reason = ""
        self._today = DayRecord(trade_date, self.equity, min_equity=self.equity, max_equity=self.equity)

    def _close_day(self) -> None:
        t = self._today
        assert t is not None
        eq = self.equity
        if self.rules.trailing_mode is TrailingMode.END_OF_DAY:
            self.hwm = max(self.hwm, eq)
            self._raise_threshold(self.hwm)
        t.end_balance = eq
        t.pnl = eq - t.start_balance
        t.min_equity, t.max_equity = self.day_min_equity, self.day_max_equity
        t.threshold_eod = self.threshold
        self.history.append(t)
        self._today = None

    def finalize(self) -> None:
        """Cierra el día en curso (fin de backtest)."""
        if self._today is not None:
            self._close_day()

    # ------------------------------------------------------------------ #
    def on_trade_closed(self, net_pnl: float, ts: datetime) -> None:
        """Registra el resultado de una operación cerrada (ya incluido en ``balance`` vía fills)."""
        self.trade_pnls.append(net_pnl)
        if net_pnl < 0:
            self.consecutive_losses += 1
            self.last_loss_ts = ts
        else:
            self.consecutive_losses = 0

    def on_fill(self, realized_pnl: float, commission: float, opened: bool) -> None:
        self.balance += realized_pnl - commission
        self.total_commissions += commission
        if self._today is not None:
            self._today.commissions += commission
            if opened:
                self._today.trades += 1
        if opened:
            self.trades_today += 1

    def mark(
        self,
        open_pnl: float,
        ts: datetime | None = None,
        open_pnl_low: float | None = None,
        open_pnl_high: float | None = None,
        equity_high: float | None = None,
    ) -> None:
        """Marca a mercado. ``low``/``high``: peor/mejor PnL abierto dentro de la barra.

        ``equity_high``: máximo de equity alcanzable en la barra por posiciones que se
        cerraron DENTRO de ella (p.ej. tocaron el máximo y luego el stop). Con trailing
        intradía la firma también lo cuenta, así que se incluye (pesimista).
        """
        lo = open_pnl if open_pnl_low is None else min(open_pnl_low, open_pnl)
        hi = open_pnl if open_pnl_high is None else max(open_pnl_high, open_pnl)
        eq_hi, eq_lo = self.balance + hi, self.balance + lo
        if equity_high is not None:
            eq_hi = max(eq_hi, equity_high)
        if self.rules.trailing_mode is TrailingMode.INTRADAY:
            if eq_hi > self.hwm:  # pesimista: el máximo ocurre antes que el mínimo
                self.hwm = eq_hi
                self._raise_threshold(self.hwm)
        self.day_min_equity = min(self.day_min_equity, eq_lo)
        self.day_max_equity = max(self.day_max_equity, eq_hi)
        self.open_pnl = open_pnl
        self._check_breach(eq_lo)

    def _check_breach(self, eq_lo: float) -> None:
        if self.breached:
            return
        if eq_lo <= self.threshold + 1e-9:
            self.breached = True
            self.breach_reason = f"MAX LOSS: equity {eq_lo:.2f} <= umbral {self.threshold:.2f}"
            return
        dll = self.rules.daily_loss_limit
        if dll is not None and eq_lo - self.day_start_balance <= -dll + 1e-9:
            if self.rules.daily_loss_mode == "breach":
                self.breached = True
                self.breach_reason = f"DAILY LOSS LIMIT: {eq_lo - self.day_start_balance:.2f} <= -{dll:.2f}"
            elif not self.day_locked:
                self.day_locked = True
                self.day_lock_reason = f"Daily loss limit de la firma alcanzado ({-dll:.2f})"

    # ------------------------------------------------------------------ #
    def best_day_share(self) -> float | None:
        """Mejor día / beneficio total (regla de consistencia). ``None`` si no hay beneficio."""
        days = [d.pnl for d in self.history] + ([self.daily_pnl] if self._today else [])
        total = sum(days)
        if total <= 0:
            return None
        return max(days) / total

    def target_reached(self) -> bool:
        r = self.rules
        if self.breached or self.total_pnl < r.profit_target:
            return False
        if self.trading_days < r.min_trading_days:
            return False
        share = self.best_day_share()
        if r.consistency_max_day_share is not None and share is not None:
            return share <= r.consistency_max_day_share
        return True

    def snapshot(self) -> dict[str, object]:
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "open_pnl": round(self.open_pnl, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "hwm": round(self.hwm, 2),
            "threshold": round(self.threshold, 2),
            "trailing_room": round(self.trailing_room, 2),
            "dd_utilization": round(self.dd_utilization, 4),
            "trades_today": self.trades_today,
            "consecutive_losses": self.consecutive_losses,
            "breached": self.breached,
            "breach_reason": self.breach_reason,
            "day_locked": self.day_locked,
            "total_pnl": round(self.total_pnl, 2),
            "trading_days": self.trading_days,
            "best_day_share": self.best_day_share(),
            "target_reached": self.target_reached(),
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
        }

    def history_dicts(self) -> list[dict[str, object]]:
        return [asdict(d) for d in self.history]
