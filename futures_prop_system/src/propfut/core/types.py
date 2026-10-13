"""Tipos de dominio compartidos por todos los módulos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum


class Side(IntEnum):
    """Dirección de una posición u orden. El valor entero es el signo."""

    LONG = 1
    SHORT = -1

    @property
    def opposite(self) -> "Side":
        return Side(-self.value)

    @classmethod
    def from_sign(cls, x: float) -> "Side":
        if x == 0:
            raise ValueError("No se puede derivar un lado de un signo 0")
        return cls.LONG if x > 0 else cls.SHORT


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"


class OrderStatus(str, Enum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    HELD = "HELD"  # orden hija de un bracket a la espera de que se llene la entrada
    WORKING = "WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }


class RunMode(str, Enum):
    """Modos de operación del sistema."""

    BACKTEST = "backtest"
    PAPER = "paper"
    ANALYSIS = "analysis"  # sólo señales, nunca envía órdenes
    LIVE_PROPOSAL = "live_proposal"  # propone; un humano confirma
    LIVE_AUTO = "live_auto"  # ejecución automática con límites estrictos


@dataclass(frozen=True, slots=True)
class Bar:
    """Barra OHLCV de un contrato concreto (o de una serie continua)."""

    ts: datetime
    root: str
    contract: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    open_interest: float | None = None

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"Barra inválida {self.contract}@{self.ts}: high < low")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(f"Barra inválida {self.contract}@{self.ts}: open/close fuera de rango")
