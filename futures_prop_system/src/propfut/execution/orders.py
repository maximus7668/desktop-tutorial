"""Modelos de órdenes, fills, posiciones y operaciones cerradas."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime

from propfut.core.types import OrderStatus, OrderType, Side, TimeInForce

_ids = itertools.count(1)


def next_id(prefix: str = "O") -> str:
    return f"{prefix}{next(_ids):07d}"


@dataclass
class Order:
    root: str
    contract: str
    side: Side
    qty: int
    type: OrderType
    tag: str  # entry | stop | target | exit | flatten | roll
    created_ts: datetime
    limit_price: float | None = None
    stop_price: float | None = None
    tif: TimeInForce = TimeInForce.DAY
    parent_id: str | None = None
    oco_group: str | None = None
    status: OrderStatus = OrderStatus.WORKING
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    expected_price: float | None = None
    bars_alive: int = 0
    reject_reason: str = ""
    id: str = field(default_factory=next_id)
    #: True si la orden se activó en la barra actual (los targets no se evalúan hasta la siguiente)
    activated_this_bar: bool = False

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError("qty debe ser > 0")
        if self.type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self.limit_price is None:
            raise ValueError(f"{self.type} requiere limit_price")
        if self.type in (OrderType.STOP, OrderType.STOP_LIMIT) and self.stop_price is None:
            raise ValueError(f"{self.type} requiere stop_price")

    @property
    def remaining(self) -> int:
        return self.qty - self.filled_qty

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.WORKING, OrderStatus.PARTIALLY_FILLED)

    def apply_fill(self, qty: int, price: float) -> None:
        if qty <= 0 or qty > self.remaining:
            raise ValueError(f"Fill inválido {qty} para orden {self.id} (restante {self.remaining})")
        total = self.avg_fill_price * self.filled_qty + price * qty
        self.filled_qty += qty
        self.avg_fill_price = total / self.filled_qty
        self.status = OrderStatus.FILLED if self.remaining == 0 else OrderStatus.PARTIALLY_FILLED


@dataclass(frozen=True, slots=True)
class Fill:
    order_id: str
    root: str
    contract: str
    side: Side
    qty: int
    price: float
    ts: datetime
    commission: float
    tag: str
    slippage_ticks: float = 0.0


@dataclass
class Position:
    root: str
    contract: str
    qty: int = 0  # con signo
    avg_price: float = 0.0
    stop_price: float | None = None
    target_price: float | None = None
    entry_ts: datetime | None = None
    initial_stop: float | None = None
    bars_held: int = 0
    best_price: float | None = None
    worst_price: float | None = None
    trade_id: str | None = None
    meta: dict[str, object] = field(default_factory=dict)

    @property
    def side(self) -> Side | None:
        return None if self.qty == 0 else Side.from_sign(self.qty)

    def apply_fill(self, side: Side, qty: int, price: float, multiplier: float) -> tuple[float, bool]:
        """Aplica un fill. Devuelve (PnL realizado bruto, ¿abrió una posición nueva desde 0?)."""
        dq = int(side) * qty
        opened = self.qty == 0
        if self.qty == 0 or (self.qty > 0) == (dq > 0):
            new_qty = self.qty + dq
            self.avg_price = (self.avg_price * abs(self.qty) + price * qty) / abs(new_qty)
            self.qty = new_qty
            return 0.0, opened
        closing = min(abs(self.qty), qty)
        sign = 1 if self.qty > 0 else -1
        realized = (price - self.avg_price) * sign * closing * multiplier
        self.qty += int(side) * closing
        rest = qty - closing
        if rest > 0:  # reversión (no la genera el sistema, pero se soporta)
            self.qty = int(side) * rest
            self.avg_price = price
            return realized, True
        if self.qty == 0:
            self.avg_price = 0.0
        return realized, False


@dataclass
class TradeRecord:
    trade_id: str
    root: str
    contract: str
    side: Side
    qty: int
    entry_ts: datetime
    entry_price: float
    exit_ts: datetime | None = None
    exit_price: float | None = None
    gross_pnl: float = 0.0
    commissions: float = 0.0
    exit_reason: str = ""
    initial_risk_usd: float = 0.0
    mae_usd: float = 0.0
    mfe_usd: float = 0.0
    bars_held: int = 0
    regime: str = ""
    confidence: float = 0.0
    explanation: str = ""

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.commissions

    @property
    def r_multiple(self) -> float:
        return self.net_pnl / self.initial_risk_usd if self.initial_risk_usd > 0 else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id, "root": self.root, "contract": self.contract,
            "side": self.side.name, "qty": self.qty,
            "entry_ts": self.entry_ts.isoformat(), "entry_price": self.entry_price,
            "exit_ts": self.exit_ts.isoformat() if self.exit_ts else None, "exit_price": self.exit_price,
            "gross_pnl": round(self.gross_pnl, 2), "commissions": round(self.commissions, 2),
            "net_pnl": round(self.net_pnl, 2), "r_multiple": round(self.r_multiple, 3),
            "exit_reason": self.exit_reason, "initial_risk_usd": round(self.initial_risk_usd, 2),
            "mae_usd": round(self.mae_usd, 2), "mfe_usd": round(self.mfe_usd, 2),
            "bars_held": self.bars_held, "regime": self.regime, "confidence": round(self.confidence, 3),
            "explanation": self.explanation,
        }
